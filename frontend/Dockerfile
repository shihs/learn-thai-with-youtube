# 第一階段：打包前端
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# 瀏覽器連後端用的網址，打包時就會寫進程式裡
ARG VITE_API_URL=http://127.0.0.1:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# 第二階段：用 nginx 提供打包好的靜態檔
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
