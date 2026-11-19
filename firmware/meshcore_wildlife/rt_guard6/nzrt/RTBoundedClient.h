#pragma once
#include <WiFiClient.h>
#include <lwip/sockets.h>
#include <errno.h>

// HTTPClient's inactivity timeout is not a whole-transfer deadline. In
// Arduino-ESP32 2.0.17 WiFiClient::write resets its retry counter whenever
// any bytes are accepted; a slow/stalled peer can monopolise the main loop.
// Use non-blocking sends and one wall-clock budget across headers/body/ACK.
class RTBoundedClient : public WiFiClient {
  uint32_t started_ = millis();
  bool timedOut_ = false;
public:
  uint32_t sendCalls=0, blockedCalls=0, bytesSent=0;
  static constexpr uint32_t LIMIT_MS = 20000;
  bool budget() {
    if (timedOut_ || uint32_t(millis()-started_) >= LIMIT_MS) {
      timedOut_=true; WiFiClient::stop(); return false;
    }
    return true;
  }
  bool timedOut() const { return timedOut_; }
  using WiFiClient::connect;
  int connect(const char* host, uint16_t port, int32_t timeout) override {
    if(!budget())return 0;
    int ok=WiFiClient::connect(host,port,timeout<0||timeout>2000?2000:timeout);
    return budget()?ok:0;
  }
  int connect(IPAddress ip, uint16_t port, int32_t timeout) override {
    if(!budget())return 0;
    int ok=WiFiClient::connect(ip,port,timeout<0||timeout>2000?2000:timeout);
    return budget()?ok:0;
  }
  size_t write(uint8_t b) override { return write(&b,1); }
  size_t write(const uint8_t* data, size_t size) override {
    size_t sent=0;
    uint32_t yielded=millis();
    while(sent<size && budget()) {
      int socket=fd();
      if(socket<0)break;
      size_t chunk=size-sent; if(chunk>8192)chunk=8192;
      int n=::send(socket,data+sent,chunk,MSG_DONTWAIT);
      ++sendCalls;
      if(n>0){sent+=n;bytesSent+=n;}
      else if(n<0 && errno!=EAGAIN && errno!=EWOULDBLOCK && errno!=EINTR) {
        WiFiClient::stop(); break;
      }
      if(n<=0)++blockedCalls;
      // A yield after every 1460 bytes imposed an avoidable throughput cap.
      // Batch successful writes for at most 2 ms; always yield on backpressure.
      if(n<=0 || uint32_t(millis()-yielded)>=2){delay(1);yielded=millis();}
    }
    return sent;
  }
  int available() override { return budget()?WiFiClient::available():0; }
  int read() override { return budget()?WiFiClient::read():-1; }
  int read(uint8_t* b,size_t n) override {return budget()?WiFiClient::read(b,n):-1;}
  int peek() override {return budget()?WiFiClient::peek():-1;}
  uint8_t connected() override {return budget()?WiFiClient::connected():0;}
};
