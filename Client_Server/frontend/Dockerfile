FROM node:25.8.2 AS builder

WORKDIR /app

# 先复制 package.json 安装依赖 (利用缓存)
COPY package.json package-lock.json* ./
RUN npm install

# 复制其它源代码并构建
COPY . .
RUN npm run build

# 第二阶段：使用 Nginx 托管构建后的静态文件
FROM nginx:1.29.7-perl
# 将构建产物拷贝到 Nginx 的默认静态托管目录
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
