#!/usr/bin/env bash

# Install ERDDAP on an Ubuntu/Debian VM.
#
# Defaults are intentionally pinned so that a future upstream release cannot
# silently change an installation. Override them with environment variables,
# for example:
#
#   JAVA_HEAP_MB=24576 START_SERVICE=true ./erddap_setup.sh
#
# This installer is for a new host. It deliberately refuses to overwrite an
# existing Java or Tomcat installation; upgrades should be planned separately.

set -Eeuo pipefail
IFS=$'\n\t'
umask 0027

readonly INSTALL_DIR="${INSTALL_DIR:-/usr/local}"
readonly JAVA_VERSION="${JAVA_VERSION:-25.0.1+8}"
readonly TOMCAT_VERSION="${TOMCAT_VERSION:-11.0.26}"
readonly ERDDAP_VERSION="${ERDDAP_VERSION:-2.31.1}"
readonly ERDDAP_CONTENT_VERSION="${ERDDAP_CONTENT_VERSION:-1.0.1}"
readonly JAVA_HEAP_MB="${JAVA_HEAP_MB:-32768}"
readonly TOMCAT_USER="${TOMCAT_USER:-tomcat}"
readonly TOMCAT_GROUP="${TOMCAT_GROUP:-cwatch}"
readonly BIG_PARENT_DIRECTORY="${BIG_PARENT_DIRECTORY:-/mnt/disks/erddap-data/erddap}"
readonly START_SERVICE="${START_SERVICE:-false}"

readonly JAVA_LINK="${INSTALL_DIR}/java_erddap"
readonly TOMCAT_LINK="${INSTALL_DIR}/tomcat_erddap"
readonly TOMCAT_INSTALL="${INSTALL_DIR}/apache-tomcat-${TOMCAT_VERSION}"
readonly SERVICE_NAME="tomcat-erddap.service"

# Checksums published on the official ERDDAP installation page. If a version
# is overridden, its matching checksum must also be supplied.
ERDDAP_WAR_MD5="${ERDDAP_WAR_MD5:-}"
ERDDAP_CONTENT_MD5="${ERDDAP_CONTENT_MD5:-}"

if [[ "${ERDDAP_VERSION}" == "2.31.1" && -z "${ERDDAP_WAR_MD5}" ]]; then
    ERDDAP_WAR_MD5="2f6d2b2992b3233cb918b80629a09853"
fi
if [[ "${ERDDAP_CONTENT_VERSION}" == "1.0.1" && -z "${ERDDAP_CONTENT_MD5}" ]]; then
    ERDDAP_CONTENT_MD5="98a8099e7e674da59fe35e9c96efa7b5"
fi

TEMP_DIR=""

log() {
    printf '\n==> %s\n' "$*"
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

run_as_root() {
    if (( EUID == 0 )); then
        "$@"
    else
        sudo "$@"
    fi
}

cleanup() {
    if [[ -n "${TEMP_DIR}" && -d "${TEMP_DIR}" ]]; then
        rm -rf -- "${TEMP_DIR}"
    fi
}

on_error() {
    local exit_code=$?
    printf 'ERROR: installation stopped at line %s (exit %s).\n' "${BASH_LINENO[0]}" "${exit_code}" >&2
    exit "${exit_code}"
}

trap cleanup EXIT
trap on_error ERR

usage() {
    cat <<'EOF'
Usage: ./erddap_setup.sh

Installs a pinned Java 25, Tomcat 11, and ERDDAP stack on Ubuntu/Debian.

Optional environment variables:
  JAVA_VERSION             Temurin JDK version (default: 25.0.1+8)
  TOMCAT_VERSION           Tomcat 11 version (default: 11.0.26)
  ERDDAP_VERSION           ERDDAP version (default: 2.31.1)
  ERDDAP_CONTENT_VERSION   erddapContent version (default: 1.0.1)
  JAVA_HEAP_MB             Initial and maximum JVM heap (default: 32768)
  BIG_PARENT_DIRECTORY     ERDDAP working-data directory
  TOMCAT_USER              Service account (default: tomcat)
  TOMCAT_GROUP             Shared administration group (default: cwatch)
  START_SERVICE            true to start ERDDAP after installation

When overriding either ERDDAP version, also provide ERDDAP_WAR_MD5 or
ERDDAP_CONTENT_MD5 for that exact release.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi
[[ $# -eq 0 ]] || die "Unknown argument: $1 (use --help)."

[[ "${JAVA_HEAP_MB}" =~ ^[1-9][0-9]*$ ]] || die "JAVA_HEAP_MB must be a positive integer."
[[ "${START_SERVICE}" == "true" || "${START_SERVICE}" == "false" ]] || \
    die "START_SERVICE must be true or false."
[[ -n "${ERDDAP_WAR_MD5}" ]] || \
    die "Set ERDDAP_WAR_MD5 when overriding ERDDAP_VERSION."
[[ -n "${ERDDAP_CONTENT_MD5}" ]] || \
    die "Set ERDDAP_CONTENT_MD5 when overriding ERDDAP_CONTENT_VERSION."

command -v sudo >/dev/null 2>&1 || (( EUID == 0 )) || die "sudo is required."
if (( EUID != 0 )); then
    sudo -v || die "This installer requires sudo access."
fi

command -v apt-get >/dev/null 2>&1 || \
    die "This installer currently supports Ubuntu/Debian (apt-get) only."

[[ ! -e "${JAVA_LINK}" && ! -L "${JAVA_LINK}" ]] || \
    die "${JAVA_LINK} already exists. This installer will not overwrite it."
[[ ! -e "${TOMCAT_LINK}" && ! -L "${TOMCAT_LINK}" ]] || \
    die "${TOMCAT_LINK} already exists. This installer will not overwrite it."
[[ ! -e "${TOMCAT_INSTALL}" ]] || \
    die "${TOMCAT_INSTALL} already exists. This installer will not overwrite it."

# ERDDAP's bigParentDirectory must be on the persistent data disk, not the
# boot disk. Test the closest existing parent before installing anything.
BIG_PARENT_PARENT="${BIG_PARENT_DIRECTORY}"
while [[ ! -e "${BIG_PARENT_PARENT}" && "${BIG_PARENT_PARENT}" != "/" ]]; do
    BIG_PARENT_PARENT="$(dirname -- "${BIG_PARENT_PARENT}")"
done
[[ "${BIG_PARENT_PARENT}" != "/" ]] || \
    die "No existing parent was found for BIG_PARENT_DIRECTORY=${BIG_PARENT_DIRECTORY}."
findmnt -T "${BIG_PARENT_PARENT}" >/dev/null 2>&1 || \
    die "${BIG_PARENT_PARENT} is not on a mounted filesystem."

log "Installing operating-system dependencies"
run_as_root apt-get update
run_as_root apt-get install -y --no-install-recommends \
    ca-certificates \
    csh \
    curl \
    fontconfig \
    fonts-dejavu-core \
    libxml2-utils \
    python3 \
    tar \
    unzip

for command_name in curl python3 sha256sum sha512sum md5sum tar unzip xmllint; do
    command -v "${command_name}" >/dev/null 2>&1 || die "Missing command after dependency install: ${command_name}"
done

TEMP_DIR="$(mktemp -d -t erddap-install.XXXXXXXX)"

log "Creating the service account and shared group"
if ! getent group "${TOMCAT_GROUP}" >/dev/null; then
    run_as_root groupadd --system "${TOMCAT_GROUP}"
fi

if ! getent passwd "${TOMCAT_USER}" >/dev/null; then
    run_as_root useradd \
        --system \
        --gid "${TOMCAT_GROUP}" \
        --home-dir /nonexistent \
        --no-create-home \
        --shell /usr/sbin/nologin \
        "${TOMCAT_USER}"
else
    run_as_root usermod -a -G "${TOMCAT_GROUP}" "${TOMCAT_USER}"
fi

case "$(uname -m)" in
    x86_64) JAVA_ARCH="x64" ;;
    aarch64) JAVA_ARCH="aarch64" ;;
    *) die "Unsupported CPU architecture: $(uname -m)" ;;
esac

log "Resolving and downloading Temurin JDK ${JAVA_VERSION}"
JAVA_MAJOR="${JAVA_VERSION%%.*}"
JAVA_RELEASE_TAG="jdk-${JAVA_VERSION//+/%2B}"
JAVA_FILE_VERSION="${JAVA_VERSION/+/_}"
JAVA_FILE="OpenJDK${JAVA_MAJOR}U-jdk_${JAVA_ARCH}_linux_hotspot_${JAVA_FILE_VERSION}.tar.gz"
JAVA_BASE_URL="https://github.com/adoptium/temurin${JAVA_MAJOR}-binaries/releases/download/${JAVA_RELEASE_TAG}"
curl --fail --location --show-error --retry 3 --retry-all-errors \
    --output "${TEMP_DIR}/${JAVA_FILE}" "${JAVA_BASE_URL}/${JAVA_FILE}"
curl --fail --location --show-error --retry 3 --retry-all-errors \
    --output "${TEMP_DIR}/${JAVA_FILE}.sha256.txt" "${JAVA_BASE_URL}/${JAVA_FILE}.sha256.txt"
JAVA_EXPECTED_SHA256="$(awk '{print $1}' "${TEMP_DIR}/${JAVA_FILE}.sha256.txt")"
JAVA_ACTUAL_SHA256="$(sha256sum "${TEMP_DIR}/${JAVA_FILE}" | awk '{print $1}')"
[[ "${JAVA_ACTUAL_SHA256}" == "${JAVA_EXPECTED_SHA256}" ]] || \
    die "Temurin JDK checksum verification failed."

mkdir "${TEMP_DIR}/java"
tar -xzf "${TEMP_DIR}/${JAVA_FILE}" -C "${TEMP_DIR}/java"
JAVA_EXTRACTED="$(find "${TEMP_DIR}/java" -mindepth 1 -maxdepth 1 -type d -print -quit)"
[[ -n "${JAVA_EXTRACTED}" ]] || die "The JDK archive did not contain a top-level directory."
JAVA_INSTALL="${INSTALL_DIR}/$(basename -- "${JAVA_EXTRACTED}")"
[[ ! -e "${JAVA_INSTALL}" ]] || die "${JAVA_INSTALL} already exists."
run_as_root mv "${JAVA_EXTRACTED}" "${JAVA_INSTALL}"
run_as_root chown -R root:root "${JAVA_INSTALL}"
run_as_root ln -s "${JAVA_INSTALL}" "${JAVA_LINK}"
"${JAVA_LINK}/bin/java" -version

log "Downloading and verifying Apache Tomcat ${TOMCAT_VERSION}"
TOMCAT_FILE="apache-tomcat-${TOMCAT_VERSION}.tar.gz"
TOMCAT_BASE_URL="https://dlcdn.apache.org/tomcat/tomcat-11/v${TOMCAT_VERSION}/bin"
curl --fail --location --show-error --retry 3 --retry-all-errors \
    --output "${TEMP_DIR}/${TOMCAT_FILE}" "${TOMCAT_BASE_URL}/${TOMCAT_FILE}"
curl --fail --location --show-error --retry 3 --retry-all-errors \
    --output "${TEMP_DIR}/${TOMCAT_FILE}.sha512" "${TOMCAT_BASE_URL}/${TOMCAT_FILE}.sha512"
TOMCAT_EXPECTED_SHA512="$(awk '{print $1}' "${TEMP_DIR}/${TOMCAT_FILE}.sha512")"
TOMCAT_ACTUAL_SHA512="$(sha512sum "${TEMP_DIR}/${TOMCAT_FILE}" | awk '{print $1}')"
[[ "${TOMCAT_ACTUAL_SHA512}" == "${TOMCAT_EXPECTED_SHA512}" ]] || \
    die "Tomcat checksum verification failed."
run_as_root tar -xzf "${TEMP_DIR}/${TOMCAT_FILE}" -C "${INSTALL_DIR}"
run_as_root ln -s "${TOMCAT_INSTALL}" "${TOMCAT_LINK}"

log "Downloading and verifying ERDDAP ${ERDDAP_VERSION}"
ERDDAP_WAR_URL="https://github.com/ERDDAP/erddap/releases/download/v${ERDDAP_VERSION}/ERDDAP-${ERDDAP_VERSION}.war"
ERDDAP_CONTENT_URL="https://github.com/ERDDAP/erddapContent/releases/download/content${ERDDAP_CONTENT_VERSION}/erddapContent.zip"

curl --fail --location --show-error --retry 3 --retry-all-errors \
    --output "${TEMP_DIR}/erddap.war" "${ERDDAP_WAR_URL}"
printf '%s  %s\n' "${ERDDAP_WAR_MD5}" "${TEMP_DIR}/erddap.war" | md5sum --check --status || \
    die "ERDDAP WAR checksum verification failed."

curl --fail --location --show-error --retry 3 --retry-all-errors \
    --output "${TEMP_DIR}/erddapContent.zip" "${ERDDAP_CONTENT_URL}"
printf '%s  %s\n' "${ERDDAP_CONTENT_MD5}" "${TEMP_DIR}/erddapContent.zip" | md5sum --check --status || \
    die "erddapContent checksum verification failed."

run_as_root install -o "${TOMCAT_USER}" -g "${TOMCAT_GROUP}" -m 0640 \
    "${TEMP_DIR}/erddap.war" "${TOMCAT_INSTALL}/webapps/erddap.war"
run_as_root unzip -q "${TEMP_DIR}/erddapContent.zip" -d "${TOMCAT_INSTALL}"
[[ -f "${TOMCAT_INSTALL}/content/erddap/setup.xml" ]] || \
    die "erddapContent did not create content/erddap/setup.xml."
[[ -f "${TOMCAT_INSTALL}/content/erddap/datasets.xml" ]] || \
    die "erddapContent did not create content/erddap/datasets.xml."

log "Creating ERDDAP's persistent working directory"
run_as_root install -d -o "${TOMCAT_USER}" -g "${TOMCAT_GROUP}" -m 2770 \
    "${BIG_PARENT_DIRECTORY}"

log "Configuring ERDDAP and Tomcat"
run_as_root cp -a "${TOMCAT_INSTALL}/conf/server.xml" "${TOMCAT_INSTALL}/conf/server.xml.original"
run_as_root cp -a "${TOMCAT_INSTALL}/conf/context.xml" "${TOMCAT_INSTALL}/conf/context.xml.original"
run_as_root cp -a "${TOMCAT_INSTALL}/content/erddap/setup.xml" \
    "${TOMCAT_INSTALL}/content/erddap/setup.xml.original"

run_as_root python3 - "${TOMCAT_INSTALL}" "${BIG_PARENT_DIRECTORY}" <<'PY'
import re
import sys
from pathlib import Path

tomcat = Path(sys.argv[1])
big_parent = sys.argv[2].rstrip("/") + "/"

context_path = tomcat / "conf" / "context.xml"
context = context_path.read_text(encoding="utf-8")
if re.search(r"<Resources\b[^>]*/>", context):
    context = re.sub(
        r"<Resources\b[^>]*/>",
        '<Resources cachingAllowed="true" cacheMaxSize="80000" />',
        context,
        count=1,
    )
else:
    context = context.replace(
        "</Context>",
        '    <Resources cachingAllowed="true" cacheMaxSize="80000" />\n</Context>',
    )
context_path.write_text(context, encoding="utf-8")

server_path = tomcat / "conf" / "server.xml"
server = server_path.read_text(encoding="utf-8")
match = re.search(r'<Connector\s+port="8080"\b[^>]*?/?>', server, flags=re.DOTALL)
if not match:
    raise SystemExit("Could not find Tomcat's active port 8080 connector")

connector = match.group(0)
attributes = {
    "connectionTimeout": "300000",
    "compression": "on",
    "compressionMinSize": "1000",
    "compressibleMimeType": "text/html,text/xml,text/plain,text/css,application/json,application/javascript,application/octet-stream",
    "maxThreads": "200",
    "relaxedQueryChars": "[]|",
}
for name, value in attributes.items():
    pattern = rf'\s+{re.escape(name)}=(?:"[^"]*"|\'[^\']*\')'
    replacement = f'\n               {name}="{value}"'
    if re.search(pattern, connector):
        connector = re.sub(pattern, replacement, connector)
    else:
        connector = re.sub(r"\s*/?>$", replacement + " />", connector)
server = server[: match.start()] + connector + server[match.end() :]

if "org.apache.catalina.valves.ErrorReportValve" not in server:
    valve = (
        '        <Valve className="org.apache.catalina.valves.ErrorReportValve" '
        'showReport="false" showServerInfo="false" />\n'
    )
    server, count = re.subn(r"(\s*</Host>)", "\n" + valve + r"\1", server, count=1)
    if count != 1:
        raise SystemExit("Could not locate </Host> in server.xml")
server_path.write_text(server, encoding="utf-8")

setup_path = tomcat / "content" / "erddap" / "setup.xml"
setup = setup_path.read_text(encoding="utf-8")
setup, count = re.subn(
    r"<bigParentDirectory>.*?</bigParentDirectory>",
    f"<bigParentDirectory>{big_parent}</bigParentDirectory>",
    setup,
    count=1,
    flags=re.DOTALL,
)
if count != 1:
    raise SystemExit("Could not find bigParentDirectory in setup.xml")
setup_path.write_text(setup, encoding="utf-8")
PY

run_as_root tee "${TOMCAT_INSTALL}/bin/setenv.sh" >/dev/null <<EOF
#!/usr/bin/env bash
umask 0007
export JAVA_HOME="${JAVA_LINK}"
export CATALINA_HOME="${TOMCAT_LINK}"
export CATALINA_BASE="${TOMCAT_LINK}"
export CATALINA_PID="${TOMCAT_LINK}/temp/catalina.pid"
export PATH="\${PATH}:\${JAVA_HOME}/bin"
export JAVA_OPTS="-server -Djava.awt.headless=true -Duser.timezone=US/Pacific -Xms${JAVA_HEAP_MB}M -Xmx${JAVA_HEAP_MB}M"
EOF
run_as_root chmod 0750 "${TOMCAT_INSTALL}/bin/setenv.sh"

# Remove applications that are unnecessary on a dedicated ERDDAP host.
for default_app in docs examples host-manager manager; do
    run_as_root rm -rf -- "${TOMCAT_INSTALL}/webapps/${default_app}"
done

run_as_root chown -R "${TOMCAT_USER}:${TOMCAT_GROUP}" "${TOMCAT_INSTALL}"
run_as_root chmod -R o-rwx "${TOMCAT_INSTALL}"
run_as_root find "${TOMCAT_INSTALL}/bin" -maxdepth 1 -type f -name '*.sh' \
    -exec chmod 0750 '{}' +
run_as_root chmod 0750 "${TOMCAT_INSTALL}/content/erddap"
run_as_root chmod 0640 \
    "${TOMCAT_INSTALL}/content/erddap/setup.xml" \
    "${TOMCAT_INSTALL}/content/erddap/datasets.xml"

run_as_root xmllint --noout "${TOMCAT_INSTALL}/conf/server.xml"
run_as_root xmllint --noout "${TOMCAT_INSTALL}/conf/context.xml"
run_as_root xmllint --noout "${TOMCAT_INSTALL}/content/erddap/setup.xml"

log "Installing the systemd service"
run_as_root tee "/etc/systemd/system/${SERVICE_NAME}" >/dev/null <<EOF
[Unit]
Description=Apache Tomcat for ERDDAP
Documentation=https://erddap.github.io/docs/server-admin/deploy-install
Wants=network-online.target
After=network-online.target
RequiresMountsFor=${BIG_PARENT_DIRECTORY}

[Service]
Type=simple
User=${TOMCAT_USER}
Group=${TOMCAT_GROUP}
UMask=0007
Environment=JAVA_HOME=${JAVA_LINK}
Environment=CATALINA_HOME=${TOMCAT_LINK}
Environment=CATALINA_BASE=${TOMCAT_LINK}
ExecStart=${TOMCAT_LINK}/bin/catalina.sh run
SuccessExitStatus=143
Restart=on-failure
RestartSec=10
TimeoutStartSec=300
TimeoutStopSec=90
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
run_as_root systemctl daemon-reload
run_as_root systemctl enable "${SERVICE_NAME}"

if [[ "${START_SERVICE}" == "true" ]]; then
    log "Starting ERDDAP"
    run_as_root systemctl start "${SERVICE_NAME}"
    run_as_root systemctl --no-pager --full status "${SERVICE_NAME}"
fi

cat <<EOF

ERDDAP installation completed successfully.

  Java:               ${JAVA_VERSION} (${JAVA_LINK})
  Tomcat:             ${TOMCAT_VERSION} (${TOMCAT_LINK})
  ERDDAP:             ${ERDDAP_VERSION}
  JVM heap:           ${JAVA_HEAP_MB} MB
  bigParentDirectory: ${BIG_PARENT_DIRECTORY}/
  Service:            ${SERVICE_NAME}

Before starting the service, edit:
  ${TOMCAT_LINK}/content/erddap/setup.xml
  ${TOMCAT_LINK}/content/erddap/datasets.xml

Then run:
  sudo systemctl start ${SERVICE_NAME}
  sudo journalctl -u ${SERVICE_NAME} -f

Local health check:
  curl -I http://127.0.0.1:8080/erddap/index.html
EOF
