# AutoUGC-TH frontend: node build → nginx static serve.
# Integration wires this service into docker-compose separately (frontend owns only this file).

# ---- build stage ----
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
# VITE_API_BASE / VITE_WS_BASE default to same-origin; nginx proxies /api and /ws to the api service.
RUN npm run build

# ---- serve stage ----
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
