# !/usr/bin/env bash

# =====================================================
# scripts/gen_proto.sh
# =====================================================

set -euo pipefail
python -m grpc_tools.protoc -Iproto --python_out=./proto --grpc_python_out=. proto/api.proto
