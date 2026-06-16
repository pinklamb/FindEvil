FROM node:20-slim

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

ENV HOST=0.0.0.0

CMD ["sh", "-c", "npx vite preview --host 0.0.0.0 --port ${PORT:-5174}"]
