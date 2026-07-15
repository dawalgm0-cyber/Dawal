# Dev-oriented image (hot reload via mounted volume in docker-compose).
FROM node:22-alpine

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .

EXPOSE 3000
CMD ["npm", "run", "dev"]
