# 40. K8s 部署清单

> 版本：v0.6 · 2026-05-06

---

## 命名空间

```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: agent-factory
---
apiVersion: v1
kind: Namespace
metadata:
  name: agent-factory-staging
```

---

## Core 服务 Deployment

```yaml
# k8s/core-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-factory-core
  namespace: agent-factory
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: agent-factory-core
  template:
    metadata:
      labels:
        app: agent-factory-core
    spec:
      containers:
        - name: core
          image: ghcr.io/agent-factory/core:latest
          ports:
            - containerPort: 8000
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: agent-factory-db
                  key: url
            - name: REDIS_URL
              valueFrom:
                secretKeyRef:
                  name: agent-factory-redis
                  key: url
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
            limits:
              cpu: 4000m
              memory: 8Gi
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
```

---

## Service

```yaml
# k8s/core-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: agent-factory-core
  namespace: agent-factory
spec:
  selector:
    app: agent-factory-core
  ports:
    - port: 80
      targetPort: 8000
  type: ClusterIP
```

---

## HPA

```yaml
# k8s/core-hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: agent-factory-core
  namespace: agent-factory
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: agent-factory-core
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
```

---

## ConfigMap

```yaml
# k8s/core-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: agent-factory-config
  namespace: agent-factory
data:
  RUNSPEC_SCHEMA_VERSION: "1"
  SESSION_TIMEOUT_MINUTES: "30"
  AUDIT_DEFAULT_LEVEL: "minimal"
  DEGRADATION_DEFAULT_LEVEL: "0"
  MODEL_DEFAULT: "qwen3-32b"
  MODEL_FALLBACK: "qwen3-14b"
```

---

## Secret

```yaml
# k8s/core-secret.yaml（模板，实际值由 CI/CD 注入）
apiVersion: v1
kind: Secret
metadata:
  name: agent-factory-secrets
  namespace: agent-factory
type: Opaque
stringData:
  jwt-secret: "<JWT_SIGNING_SECRET>"
  model-api-key: "<MODEL_API_KEY>"
```

---

---

## Doc Worker Deployment

```yaml
# k8s/doc-worker-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-factory-doc-worker
  namespace: agent-factory
spec:
  replicas: 3
  selector:
    matchLabels:
      app: agent-factory-doc-worker
  template:
    metadata:
      labels:
        app: agent-factory-doc-worker
    spec:
      containers:
        - name: doc-worker
          image: ghcr.io/agent-factory/doc-worker:latest
          env:
            - name: REDIS_URL
              valueFrom:
                secretKeyRef:
                  name: agent-factory-redis
                  key: url
            - name: MINIO_ENDPOINT
              valueFrom:
                secretKeyRef:
                  name: agent-factory-minio
                  key: endpoint
          resources:
            requests:
              cpu: 500m
              memory: 512Mi
            limits:
              cpu: 2000m
              memory: 2048Mi          # OCR 任务需 2GB
          livenessProbe:
            exec:
              command:
                - python
                - -c
                - "import sys; sys.exit(0)"
            initialDelaySeconds: 10
            periodSeconds: 30
```

## Doc Worker HPA

```yaml
# k8s/doc-worker-hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: agent-factory-doc-worker
  namespace: agent-factory
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: agent-factory-doc-worker
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Pods
      pods:
        metric:
          name: doc_worker_queue_length
        target:
          type: AverageValue
          averageValue: "1000"
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
```

---

## 与现有文档的衔接

- **部署拓扑** → [18-deployment-ops.md](18-deployment-ops.md)
- **CI/CD 配置** → [28-cicd.md](28-cicd.md)
- **容量规划** → [18-deployment-ops.md](18-deployment-ops.md) §容量规划
- **文档解析 Worker** → [24-document-parser-worker.md](24-document-parser-worker.md)
