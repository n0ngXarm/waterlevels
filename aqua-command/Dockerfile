FROM node:22-alpine
WORKDIR /app
COPY package.json server.mjs rules.mjs ./
COPY public ./public
RUN mkdir -p /app/storage && chown -R node:node /app
USER node
ENV NODE_ENV=production HOST=0.0.0.0 PORT=8787
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 CMD node -e "fetch('http://127.0.0.1:8787/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.mjs"]
