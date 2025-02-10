FROM alpine:3.19

RUN apk update && \
    apk --no-cache add dnsmasq

RUN mkdir /tftp

ENTRYPOINT ["dnsmasq", "-k", "--log-queries", "--log-dhcp", "--no-daemon"]
