#!/usr/bin/env bash

echo "=-=-=-=-=-=-=-=-=-"
echo "Create A Pool:"
pool_id=`grpcurl -plaintext -import-path proto -proto proto/api.proto -d '{"spec": {"name":"prod","tenant_id":"tony"} }' localhost:50051 devbox.ControllerAPI/CreatePool | jq '.["pool"]["id"]'`

echo -n "pool id: "
echo $pool_id

#sleep 1

echo ""
echo "=-=-=-=-=-=-=-=-=-"
echo "Now we we ask Forky to create 3 hosts ready to go into pool_id=$pool_id:"

grpcurl -plaintext -import-path proto -proto proto/api.proto -d '{ "pool_id": '$pool_id', "shape":{"vcpu":8,"ram_gb":32,"gpu_model":"nvidia"}, "target":1 }' localhost:50051 devbox.ControllerAPI/EnsureWarmPool 

#sleep 1

echo ""
echo "=-=-=-=-=-=-=-=-=-"
echo "Now the pool contains:"

grpcurl -plaintext -import-path proto -proto proto/api.proto -d '{ "pool_id": '$pool_id'}' localhost:50051 devbox.ControllerAPI/ListPoolHosts


vm_id=`grpcurl -plaintext -import-path proto -proto proto/api.proto -d '{ "pool_id": '$pool_id'}' localhost:50051 devbox.ControllerAPI/ListPoolHosts | jq '.["hosts"][0]'`

#sleep 1

echo -n "vm id: "
echo $vm_id
if [ -z $vm_id ]; then
  echo "no valid vm_id found"
  exit 1
fi

echo ""
echo "=-=-=-=-=-=-=-=-=-"
echo "Now we fork FOUR instances from $vm_id:"

grpcurl -plaintext -import-path proto -proto proto/api.proto -d '{ "how_many": 4, "vm_id": '$vm_id', "cold_fork": "true" }' localhost:50051 devbox.ControllerAPI/Fork

echo ""
echo "=-=-=-=-=-=-=-=-=-"
echo "Now the pool contains:"

grpcurl -plaintext -import-path proto -proto proto/api.proto -d '{ "pool_id": '$pool_id'}' localhost:50051 devbox.ControllerAPI/ListPoolHosts
