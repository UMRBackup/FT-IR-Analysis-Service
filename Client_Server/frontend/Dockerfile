FROM node:25.8.2 AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

FROM nginx:1.29.7-perl
COPY --from=builder /app/dist /usr/share/nginx/html

# 因为这是一个 React/Vite 单页应用 (SPA)，对于前端路由刷新时可能报 404
# 我们在容器内加一个简单的 Nginx SPA fallback 配置
RUN echo "server { \
    listen       80; \
    server_name  localhost; \
    location / { \
        root   /usr/share/nginx/html; \
        index  index.html index.htm; \
        try_files \$uri \$uri/ /index.html; \
    } \
}" > /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
