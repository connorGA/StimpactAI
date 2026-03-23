FROM node:22-alpine AS deps

WORKDIR /app/client-ui
COPY client-ui/package.json client-ui/package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder

WORKDIR /app/client-ui
COPY --from=deps /app/client-ui/node_modules ./node_modules
COPY client-ui ./
RUN npm run build

FROM node:22-alpine AS runner

ENV NODE_ENV=production
WORKDIR /app/client-ui

COPY --from=builder /app/client-ui/.next ./.next
COPY --from=builder /app/client-ui/package.json ./package.json
COPY --from=deps /app/client-ui/node_modules ./node_modules

EXPOSE 3000

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
