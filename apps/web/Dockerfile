# The web image. Multi-stage, standalone output, non-root.

FROM node:22-slim AS deps
WORKDIR /app
# `npm ci` from the lockfile, not `npm install`: the same reason the API pins
# hashes. An image resolved fresh is an image nobody tested.
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-slim AS run
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# `output: 'standalone'` traces the modules actually imported and copies them
# beside a minimal server. The alternative is shipping `node_modules` — several
# hundred megabytes of build-time tooling in a runtime image.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

# The node image already has a `node` user at 1000. Using it is one less
# account than creating our own, and the point is only that it is not root.
USER node

EXPOSE 3000

# No curl in this image, and no reason to add one: node can make the request.
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
