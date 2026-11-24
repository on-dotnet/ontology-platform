# OWL API round-trip tool for ./dev.ps1 owl-check (image ontology/owlapi:<workspace tag>).
# Development only: never part of the runtime images.

FROM maven:3.9-eclipse-temurin-25 AS build

# Optional Maven mirror (dev/mirrors.cn.env sets one); empty means Maven Central.
ARG MAVEN_MIRROR=
WORKDIR /build
COPY pom.xml ./
COPY src ./src
RUN set -eu; \
    if [ -n "$MAVEN_MIRROR" ]; then \
      printf '<settings><mirrors><mirror><id>mirror</id><mirrorOf>*</mirrorOf><url>%s</url></mirror></mirrors></settings>\n' "$MAVEN_MIRROR" > /tmp/settings.xml; \
      set -- -s /tmp/settings.xml; \
    fi; \
    mvn -q -B "$@" package dependency:copy-dependencies -DincludeScope=runtime

FROM eclipse-temurin:25-jre

COPY --from=build /build/target/owl-roundtrip-0.jar /opt/owlapi/
COPY --from=build /build/target/dependency/ /opt/owlapi/lib/
RUN useradd --system --uid 10001 --no-create-home owlapi && mkdir -p /work && chown owlapi /work
USER owlapi
WORKDIR /work
ENTRYPOINT ["java", "-cp", "/opt/owlapi/owl-roundtrip-0.jar:/opt/owlapi/lib/*", "RoundTrip"]
