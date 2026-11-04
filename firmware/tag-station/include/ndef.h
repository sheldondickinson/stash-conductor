#pragma once
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
namespace ndef {
inline std::vector<uint8_t> uri(const std::string &url) {
 if(url.rfind("https://",0)!=0 || url.size()>120)return {};
 std::string tail=url.substr(8);
 std::vector<uint8_t> r={0x03,uint8_t(tail.size()+5),0xd1,0x01,uint8_t(tail.size()+1),0x55,0x04};
 r.insert(r.end(),tail.begin(),tail.end());r.push_back(0xfe);while(r.size()%4)r.push_back(0);return r;
}
inline std::string parse(const uint8_t *p,size_t n) {
 size_t i=0;while(i<n&&p[i]==0)i++;
 if(i+7>n||p[i]!=3)return "";
 size_t len=p[i+1];if(len==0xff||i+2+len>n||len<5)return "";
 if(p[i+2]!=0xd1||p[i+3]!=1||p[i+5]!=0x55||p[i+6]!=4||p[i+4]+4!=len)return "";
 return "https://"+std::string(reinterpret_cast<const char*>(p+i+7),len-5);
}
inline bool blank(const uint8_t *p,size_t n) {
 size_t i=0;while(i<n&&p[i]==0)i++;
 if(i==n)return true;
 if(i+2<n&&p[i]==3&&p[i+1]==0&&p[i+2]==0xfe){i+=3;while(i<n&&p[i]==0)i++;return i==n;}
 return false;
}
inline size_t capacity(uint8_t product,uint8_t subtype,uint8_t storage) {
 if(product!=4||subtype!=2)return 0;
 return storage==0x0f?144:storage==0x11?504:storage==0x13?888:0;
}
}
