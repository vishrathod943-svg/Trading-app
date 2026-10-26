#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../android"
# The cloud environment retains these verified toolchains. Local builds can use Android Studio.
if [ -d /workspace/toolchains/jdk-21.0.9+10 ]; then
    export JAVA_HOME=/workspace/toolchains/jdk-21.0.9+10
    export ANDROID_HOME=/workspace/toolchains/android-sdk
    export ANDROID_USER_HOME=/workspace/toolchains/android-user
    export GRADLE_USER_HOME=/workspace/toolchains/gradle-home
    export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts -Duser.home=/workspace/toolchains/java-user"
fi
exec ./gradlew --no-daemon --max-workers=2 assembleDebug "$@"
