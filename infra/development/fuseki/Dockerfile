# 开发镜像：Apache 官方 Fuseki 发行包；基础镜像摘要在依赖核验后固定。
FROM eclipse-temurin:21.0.12.1_1-jre-jammy@sha256:affcab5356e1270ac35d2361ee83135af2f03e8d580eca78a6d5d6fdbf048db0

ARG JENA_VERSION=6.2.0
ARG JENA_SHA512=ba65f5867d2d4741b2ed9e2af5a0d4fbb447909894ab2a0c6bc4dac8997f4fe339c87b13c48d45d054977769f0f8bf763ea346b1f7792d5cdc458041bd43a132

USER root
RUN set -eu; \
    curl --fail --location --retry 3 --output /tmp/fuseki.tar.gz "https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki-${JENA_VERSION}.tar.gz"; \
    printf '%s  %s\n' "${JENA_SHA512}" /tmp/fuseki.tar.gz | sha512sum --check --strict; \
    mkdir -p /opt/fuseki /fuseki/databases; \
    tar -xzf /tmp/fuseki.tar.gz --strip-components=1 -C /opt/fuseki; \
    rm /tmp/fuseki.tar.gz; \
    groupadd --gid 10001 fuseki; \
    useradd --uid 10001 --gid fuseki --no-create-home --home-dir /fuseki fuseki; \
    chown -R fuseki:fuseki /fuseki

COPY --chmod=0555 entrypoint.sh /opt/fuseki/entrypoint.sh
COPY --chmod=0444 g2-config.ttl g2-log4j2.properties /opt/fuseki/

ENV FUSEKI_BASE=/fuseki
WORKDIR /fuseki
USER 10001:10001
EXPOSE 3030
ENTRYPOINT ["/opt/fuseki/entrypoint.sh"]
CMD ["--tdb2", "--loc=/fuseki/databases/ontology", "--update", "/ontology"]
