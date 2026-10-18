FROM node:24-alpine AS build

WORKDIR /app
RUN npm install --global pnpm@11.19.0

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
ARG BUILD_HTTPS_PROXY="http://host.docker.internal:7897"
RUN pnpm --config.https-proxy=${BUILD_HTTPS_PROXY} --config.proxy=${BUILD_HTTPS_PROXY} install --frozen-lockfile

COPY . .
ARG VITE_AMAP_WEB_KEY=""
ARG VITE_AMAP_SECURITY_CODE=""
ENV VITE_AMAP_WEB_KEY=${VITE_AMAP_WEB_KEY} \
    VITE_AMAP_SECURITY_CODE=${VITE_AMAP_SECURITY_CODE}
ARG VITE_DISCOVERY_PRODUCT="true"
ENV VITE_DISCOVERY_PRODUCT=${VITE_DISCOVERY_PRODUCT}
ARG VITE_TRAVEL_CONTENT_CONTRACT="place-content-v1"
ARG VITE_ASSISTANT_CONTEXT_CONTRACT="assistant-context-v1"
ENV VITE_TRAVEL_CONTENT_CONTRACT=${VITE_TRAVEL_CONTENT_CONTRACT} \
    VITE_ASSISTANT_CONTEXT_CONTRACT=${VITE_ASSISTANT_CONTEXT_CONTRACT}
RUN pnpm typecheck && VITE_DISCOVERY_PRODUCT= VITE_TRAVEL_CONTENT_CONTRACT= VITE_ASSISTANT_CONTEXT_CONTRACT= pnpm test --maxWorkers=2 && pnpm build

FROM nginx:1.27-alpine AS production

COPY nginx.local-product.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
