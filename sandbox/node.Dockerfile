FROM node:24-bookworm-slim@sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553
LABEL codeatlas.profile="node-test-v1"
COPY node_runner.mjs /opt/codeatlas/node_runner.mjs
USER 65534:65534
WORKDIR /workspace
ENTRYPOINT ["/usr/bin/timeout", "--signal=KILL", "30s"]
CMD ["node", "/opt/codeatlas/node_runner.mjs"]
