FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ARG VCS_REF=unknown
RUN VITE_DEV_BYPASS_AUTH=false npm run build && rm -f dist/bundle-analysis.html dist/assets/*.map
RUN node -e "require('fs').writeFileSync('dist/ui-version.json', JSON.stringify({source_sha: process.env.VCS_REF || 'unknown'}))"

FROM nginxinc/nginx-unprivileged:stable-alpine@sha256:4714e0b1b2577eaa1a6131d07c958b67f0eb68e6d0521e90c6e5287db8cf0bc5 AS runtime
ARG VCS_REF=unknown
LABEL org.opencontainers.image.revision=$VCS_REF
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/dist/ /usr/share/nginx/html/
USER 101:101
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/ui-health || exit 1
# Configuration is immutable; entrypoint template rewriting is unnecessary.
ENTRYPOINT []
CMD ["nginx", "-g", "daemon off;"]
