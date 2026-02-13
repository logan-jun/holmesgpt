# HolmesGPT Air-Gapped Helm Chart

Air-gapped (closed network) Kubernetes environment deployment chart for HolmesGPT with vLLM support.

## Prerequisites

- Kubernetes 1.24+
- Helm 3.x
- Private container registry with the holmesgpt-airgap image
- vLLM service running in the cluster

## Build & Transfer Image

```bash
# On a machine with internet access
cd deploy/
./build.sh

# Transfer the tar file to the air-gapped environment
scp holmesgpt-airgap-latest.tar user@airgap-host:/tmp/

# On the air-gapped machine, load into local registry
docker load -i /tmp/holmesgpt-airgap-latest.tar
docker tag holmesgpt/holmesgpt-airgap:latest YOUR_REGISTRY/holmesgpt-airgap:latest
docker push YOUR_REGISTRY/holmesgpt-airgap:latest
```

## Install

```bash
helm install holmesgpt ./holmesgpt-airgap/ \
  --namespace holmes --create-namespace \
  --set registry=YOUR_REGISTRY \
  --set vllm.endpoint=http://YOUR_VLLM_SVC:8000/v1 \
  --set prometheus.url=http://prometheus-server.monitoring:9090 \
  --set grafana.url=http://grafana.monitoring:3000
```

## Key Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `registry` | Container registry | `PLACEHOLDER_REGISTRY` |
| `vllm.endpoint` | vLLM API endpoint | `http://VLLM_SERVICE...` |
| `vllm.modelName` | Model name | `gpt-oss-120b` |
| `prometheus.url` | Prometheus URL | `http://prometheus-server.monitoring:9090` |
| `grafana.url` | Grafana URL | `http://grafana.monitoring:3000` |
| `networkPolicy.enabled` | Enable NetworkPolicy | `true` |

## Verify

```bash
kubectl get pods -n holmes
kubectl logs -n holmes deployment/holmesgpt-holmes
```
