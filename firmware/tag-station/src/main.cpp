#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <SPI.h>
#include <MFRC522.h>
#include <ArduinoJson.h>
#include <Update.h>
#include <mbedtls/sha256.h>
#include "ndef.h"
// Owner selected ESP32 C3 SuperMini, 4 MB flash, native USB Serial/JTAG.
// Reader wiring avoids USB18/19 and boot strapping GPIO2/8/9.
constexpr int PIN_CS=7, PIN_RST=10, PIN_SCK=4, PIN_MOSI=6, PIN_MISO=5, PIN_LED=8;
MFRC522 reader(PIN_CS,PIN_RST); Preferences prefs; JsonDocument cfg;
String origin,station,credential,rootCA,mode="encode",lastUID;bool waitingRemoval=false;
unsigned long lastHealth=0,absentSince=0;bool armed=false,bootReported=false;unsigned long lastOnline=0;
String pendingUID,pendingReservation,pendingURL;bool pendingWritten=false;
void light(int n){for(int i=0;i<n;i++){digitalWrite(PIN_LED,LOW);delay(90);digitalWrite(PIN_LED,HIGH);delay(90);}}
String uidString(){String s;for(byte i=0;i<reader.uid.size;i++){if(reader.uid.uidByte[i]<16)s+='0';s+=String(reader.uid.uidByte[i],HEX);}s.toUpperCase();return s;}
void loadPending(){JsonDocument p;deserializeJson(p,prefs.getString("pending","{}"));pendingUID=p["uid"].as<String>();pendingReservation=p["reservation"].as<String>();pendingURL=p["url"].as<String>();}
bool remember(String uid,String reservation,String url){JsonDocument p;p["uid"]=uid;p["reservation"]=reservation;p["url"]=url;String raw;serializeJson(p,raw);prefs.putString("pending",raw);loadPending();return pendingUID==uid&&pendingReservation==reservation&&pendingURL==url;}
void clearPending(){prefs.remove("pending");loadPending();}
bool call(JsonDocument &request,JsonDocument &result){
 if(WiFi.status()!=WL_CONNECTED||rootCA.isEmpty()||time(nullptr)<1700000000)return false;
 WiFiClientSecure client;client.setCACert(rootCA.c_str());HTTPClient http;http.setTimeout(12000);
 if(!http.begin(client,origin+"/api/station/"+station+"/exchange"))return false;
 http.addHeader("Content-Type","application/json");http.addHeader("Authorization","Bearer "+credential);
 String body;serializeJson(request,body);int code=http.POST(body);
 if(code!=200){http.end();return false;}
 String response=http.getString();http.end();if(response.length()>4096)return false;
 if(deserializeJson(result,response))return false;
 lastOnline=millis();return true;
}
bool readPage(byte page,byte* data){byte n=18;byte b[18];if(reader.MIFARE_Read(page,b,&n)!=MFRC522::STATUS_OK||n<16)return false;memcpy(data,b,16);return true;}
size_t identify(){
 byte command[3]={0x60,0,0},answer[10],n=sizeof(answer),valid=0;
 if(reader.PCD_CalculateCRC(command,1,command+1)!=MFRC522::STATUS_OK)return 0;
 if(reader.PCD_TransceiveData(command,3,answer,&n,&valid,0,true)!=MFRC522::STATUS_OK||n<8)return 0;
 if(answer[1]!=4||answer[7]!=3)return 0; // NXP manufacturer, ISO14443-3 protocol
 return ndef::capacity(answer[2],answer[3],answer[6]);
}
bool readMemory(std::vector<uint8_t>&memory,size_t capacity){
 memory.resize(capacity);byte data[16];
 for(size_t at=0;at<capacity;at+=16){if(!readPage(4+at/4,data))return false;memcpy(memory.data()+at,data,std::min(size_t(16),capacity-at));}
 return true;
}
bool writable(size_t cap){
 byte data[16];if(!readPage(0,data))return false;
 if(data[10]||data[11])return false; // static locks
 if(data[12]!=0xe1||data[13]!=0x10||(data[15]&15)!=0)return false; // standard writable CC
 const byte dynamic=cap==144?40:cap==504?130:226;
 if(!readPage(dynamic,data))return false;
 if(data[0]||data[1]||data[2])return false; // dynamic locks
 if(data[7]!=0xff)return false; // AUTH0: no password protected user area
 return true;
}
void report(const String&uid,const String&detail){JsonDocument q,r;q["action"]="inspect";q["uid"]=uid;q["detail"]=detail;call(q,r);Serial.println(detail);}
bool acknowledge(const String&uid,const String&url){
 JsonDocument q,r;q["action"]="verify";q["uid"]=uid;q["reservation_id"]=pendingReservation;q["readback"]=url;
 if(!call(q,r)||!r["verified"].as<bool>())return false;
 Serial.print("Verified code: ");Serial.println(r["code"].as<String>());clearPending();light(2);return true;
}
void process(){
 String uid=uidString();lastUID=uid;waitingRemoval=true;absentSince=0;
 if(reader.uid.size!=7){Serial.println("Unsupported tag. Use NTAG213, 215 or 216.");return;}
 size_t cap=identify();if(!cap){report(uid,"Unsupported tag version. No write.");return;}
 std::vector<uint8_t> memory;if(!readMemory(memory,cap)){report(uid,"Could not read tag. No write.");return;}
 String current=ndef::parse(memory.data(),memory.size()).c_str();
 if(mode!="encode"){report(uid,current.length()?"Read URL: "+current:"Tag inspected. No HTTPS NDEF URL found.");return;}
 // Recover a completed physical write after reset or a lost acknowledgement, without rewriting.
 if(pendingUID==uid&&current==pendingURL){if(!acknowledge(uid,current))Serial.println("Readback verified locally. Server acknowledgement pending.");return;}
 if(current.startsWith(origin+"/t/")){report(uid,"Existing Stash tag recognised. Never overwritten automatically.");light(1);return;}
 if(!armed||millis()-lastOnline>20000){report(uid,"Disarmed or offline. No write.");return;}
 if(!pendingUID.isEmpty()&&pendingUID!=uid){report(uid,"Resolve the outstanding tag reservation first.");return;}
 JsonDocument q,r;q["action"]="reserve";q["uid"]=uid;q["kind"]=cap==144?"NTAG213":cap==504?"NTAG215":"NTAG216";q["blank"]=ndef::blank(memory.data(),memory.size());
 if(!call(q,r)){report(uid,"Reservation refused. Inspect, arm, or confirm overwrite in Stash.");return;}
 String reservation=r["reservation_id"], url=r["tag"]["url"];
 if(r["state"]=="skipped"){if(pendingUID==uid)clearPending();report(uid,"Skipped reservation retained. No write.");return;}
 if(!r["may_write"].as<bool>()){report(uid,"Reservation not writable.");return;}
 const bool resume=(pendingUID==uid&&pendingReservation==reservation);
 if(!ndef::blank(memory.data(),memory.size())&&!resume&&!r["overwrite"].as<bool>()){report(uid,"Nonblank tag. Confirm this UID in Stash.");return;}
 auto encoded=ndef::uri(url.c_str());if(encoded.empty()||encoded.size()>cap||!url.startsWith(origin+"/t/")||!writable(cap)){report(uid,"Capacity, lock, format or URL check failed. No write.");return;}
 if(!remember(uid,reservation,url)){report(uid,"Durable reservation storage failed. No write.");return;} // before first write
 byte empty[4]={0x03,0,0xfe,0};
 if(reader.MIFARE_Ultralight_Write(4,empty,4)!=MFRC522::STATUS_OK){report(uid,"Write failed. Reservation retained.");return;}
 // Only user pages. Length is committed last, so interruption cannot advertise a partial URL.
 for(size_t at=4;at<encoded.size();at+=4){if(reader.MIFARE_Ultralight_Write(4+at/4,encoded.data()+at,4)!=MFRC522::STATUS_OK){report(uid,"Write interrupted. Reservation retained.");return;}}
 if(reader.MIFARE_Ultralight_Write(4,encoded.data(),4)!=MFRC522::STATUS_OK){report(uid,"Final write failed. Reservation retained.");return;}
 pendingWritten=true;
 if(!readMemory(memory,cap)||String(ndef::parse(memory.data(),memory.size()).c_str())!=url){report(uid,"Readback failed. Do not advance.");return;}
 if(!acknowledge(uid,url))Serial.println("Physical readback verified. Server acknowledgement pending. Present this same tag again.");
}
void ota(const String &expected) {
 if(expected.length()!=64||armed||!pendingUID.isEmpty()){Serial.println("Disarm and resolve reservations before OTA. Supply the reviewed SHA256.");return;}
 if(WiFi.status()!=WL_CONNECTED||rootCA.isEmpty())return;
 WiFiClientSecure client;client.setCACert(rootCA.c_str());HTTPClient http;http.setTimeout(15000);
 if(!http.begin(client,origin+"/api/station/"+station+"/firmware"))return;
 http.addHeader("Authorization","Bearer "+credential);
 int code=http.GET(),length=http.getSize();
 if(code!=200||length<1||length>2*1024*1024){http.end();Serial.println("No valid staged update");return;}
 if(!Update.begin(length)){http.end();Serial.println("Update partition unavailable");return;}
 mbedtls_sha256_context hash;mbedtls_sha256_init(&hash);mbedtls_sha256_starts_ret(&hash,0);
 auto stream=http.getStreamPtr();size_t done=0;byte buffer[1024];unsigned long last=millis();
 while(done<(size_t)length&&millis()-last<15000){size_t available=stream->available();if(!available){delay(5);continue;}size_t n=stream->readBytes(buffer,std::min(sizeof(buffer),available));if(!n)break;last=millis();mbedtls_sha256_update_ret(&hash,buffer,n);if(Update.write(buffer,n)!=n)break;done+=n;}
 byte digest[32];mbedtls_sha256_finish_ret(&hash,digest);mbedtls_sha256_free(&hash);String actual;for(byte b:digest){if(b<16)actual+='0';actual+=String(b,HEX);}http.end();
 if(done!=(size_t)length||actual!=expected){Update.abort();Serial.println("Firmware length or SHA256 failed. Existing firmware retained.");return;}
 if(Update.end(true)){Serial.println("Verified firmware installed; restarting disarmed.");delay(200);ESP.restart();}else Serial.println("Update failed.");
}
void serialCommand(){
 if(!Serial.available())return;
 String line=Serial.readStringUntil('\n');line.trim();
 if(line=="inspect"||line=="verify"||line=="encode"){mode=line;armed=false;Serial.println("Mode changed; server arming still required for writes.");return;}
 if(line.startsWith("ota ")){ota(line.substring(4));return;}
 if(line.startsWith("{")){JsonDocument candidate;if(deserializeJson(candidate,line)){Serial.println("Invalid JSON");return;}
  // USB serial only. No web setup endpoint, no secrets echoed.
  if(!candidate["origin"].as<String>().startsWith("https://")||candidate["credential"].as<String>().length()<32||candidate["ca_pem"].as<String>().length()<100){Serial.println("Origin, station credential and CA certificate required");return;}
  prefs.putString("config",line);Serial.println("Configuration saved. Restarting.");delay(200);ESP.restart();
 }
}
void setup(){Serial.begin(115200);Serial.setTimeout(1500);digitalWrite(PIN_LED,HIGH);pinMode(PIN_LED,OUTPUT);prefs.begin("stash",false);loadPending();
 String data=prefs.getString("config","");if(deserializeJson(cfg,data))Serial.println("Provision over USB serial using protected config JSON.");
 origin=cfg["origin"].as<String>();station=cfg["station_id"].as<String>();credential=cfg["credential"].as<String>();rootCA=cfg["ca_pem"].as<String>();
 SPI.begin(PIN_SCK,PIN_MISO,PIN_MOSI,PIN_CS);reader.PCD_Init();byte chip=reader.PCD_ReadRegister(MFRC522::VersionReg);Serial.printf("Reader version: 0x%02x. Confirm XC4506 chipset before commissioning.\n",chip);
 if(chip!=0x91&&chip!=0x92){Serial.println("Unrecognised reader; writing disabled.");while(true){serialCommand();delay(20);}}
 WiFi.mode(WIFI_STA);if(!cfg["ssid"].as<String>().isEmpty())WiFi.begin(cfg["ssid"].as<const char*>(),cfg["wifi_password"].as<const char*>());configTime(0,0,cfg["ntp_server"] | "pool.ntp.org");
}
void loop(){serialCommand();
 if(millis()-lastHealth>10000){lastHealth=millis();JsonDocument q,r;
  if(!bootReported){q["action"]="boot";bootReported=call(q,r);armed=false;}
  else {q["action"]="health";armed=call(q,r)&&r["armed"].as<bool>()&&mode=="encode";}
 }
 if(waitingRemoval){
  // WUPA sees the same halted tag. Require sustained absence before accepting another.
  byte atqa[2],size=2;auto status=reader.PICC_WakeupA(atqa,&size);
  if(status==MFRC522::STATUS_OK||status==MFRC522::STATUS_COLLISION){absentSince=0;reader.PICC_ReadCardSerial();reader.PICC_HaltA();}
  else {if(!absentSince)absentSince=millis();if(millis()-absentSince>700){waitingRemoval=false;lastUID="";}}
  delay(80);return;
 }
 if(reader.PICC_IsNewCardPresent()&&reader.PICC_ReadCardSerial()){process();reader.PICC_HaltA();reader.PCD_StopCrypto1();}
 delay(50);
}
