#include "../include/ndef.h"
#include <cassert>
int main(){
 const std::string url="https://stash.example.com/t/abcdefghijklmnopqrstuv";
 auto bytes=ndef::uri(url);assert(bytes.size()<=144);assert(bytes.size()%4==0);
 assert(ndef::parse(bytes.data(),bytes.size())==url);
 auto truncated=bytes;truncated[1]=255;assert(ndef::parse(truncated.data(),truncated.size()).empty());
 uint8_t blank[]={3,0,0xfe,0,0,0,0,0};assert(ndef::blank(blank,sizeof blank));blank[7]=1;assert(!ndef::blank(blank,sizeof blank));
 assert(ndef::capacity(4,2,0x0f)==144);assert(ndef::capacity(4,2,0x11)==504);assert(ndef::capacity(4,2,0x13)==888);assert(ndef::capacity(3,2,0x0f)==0);
 assert(ndef::uri("http://example.com").empty());assert(ndef::uri(std::string(200,'x')).empty());
}
