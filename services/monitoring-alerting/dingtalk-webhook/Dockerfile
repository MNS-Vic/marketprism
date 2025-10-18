# Build a lightweight wrapper image to allow envsubst for templated config
FROM alpine:3.20
RUN apk add --no-cache ca-certificates tzdata bash curl gettext
# Copy binary from upstream official image
COPY --from=timonwong/prometheus-webhook-dingtalk:latest /bin/prometheus-webhook-dingtalk /bin/prometheus-webhook-dingtalk
# Config template & templates will be mounted as volumes at runtime, but add default paths
WORKDIR /etc/prometheus-webhook-dingtalk
ENTRYPOINT ["/bin/sh","-lc"]
CMD ["envsubst < /etc/prometheus-webhook-dingtalk/config.tmpl.yml > /etc/prometheus-webhook-dingtalk/config.yml && exec /bin/prometheus-webhook-dingtalk --web.enable-ui --web.enable-lifecycle --config.file=/etc/prometheus-webhook-dingtalk/config.yml"]

