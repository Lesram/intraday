# External Secrets Operator (ESO) Setup Guide

This document describes how to configure the External Secrets Operator for production deployments of the algorithmic trading platform.

## Overview

The External Secrets Operator (ESO) synchronizes secrets from external secret management systems (like HashiCorp Vault, AWS Secrets Manager, or GCP Secret Manager) into Kubernetes Secrets.

**Why ESO?**
- Centralized secret management
- Automatic secret rotation
- Audit trail for secret access
- No secrets in version control
- Environment-specific configurations

## Prerequisites

1. Kubernetes cluster (1.19+)
2. Helm 3.x
3. Access to a secrets backend (Vault, AWS SM, GCP SM, Azure KV)
4. `kubectl` configured for your cluster

## Installation

### 1. Install External Secrets Operator

```bash
# Add the ESO Helm repository
helm repo add external-secrets https://charts.external-secrets.io
helm repo update

# Install ESO in the external-secrets namespace
helm install external-secrets \
  external-secrets/external-secrets \
  -n external-secrets \
  --create-namespace \
  --set installCRDs=true
```

### 2. Verify Installation

```bash
kubectl -n external-secrets get pods
# Should show external-secrets pods running

kubectl get crd | grep external
# Should show externalsecrets.external-secrets.io, secretstores, etc.
```

## Configuration

### Option A: HashiCorp Vault Backend

#### Create ClusterSecretStore

```yaml
# k8s/vault-secret-store.yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: vault-backend
spec:
  provider:
    vault:
      server: "https://vault.example.com"
      path: "secret"
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "algotrading-role"
          serviceAccountRef:
            name: "algotrading-sa"
            namespace: "algotrading"
```

Apply:
```bash
kubectl apply -f k8s/vault-secret-store.yaml
```

### Option B: AWS Secrets Manager Backend

#### Create IAM Role and Service Account

```yaml
# k8s/aws-secret-store.yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: aws-secrets-manager
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1
      auth:
        jwt:
          serviceAccountRef:
            name: algotrading-sa
            namespace: algotrading
```

### Option C: GCP Secret Manager Backend

```yaml
# k8s/gcp-secret-store.yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: gcp-secret-manager
spec:
  provider:
    gcpsm:
      projectID: your-gcp-project
      auth:
        workloadIdentity:
          clusterLocation: us-central1
          clusterName: algotrading-cluster
          serviceAccountRef:
            name: algotrading-sa
            namespace: algotrading
```

## Creating External Secrets

### Main Application Secrets

The `k8s/secrets.yaml` file contains a commented ESO template. To use ESO:

```yaml
# k8s/external-secret-algotrading.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: algotrading-external-secrets
  namespace: algotrading
spec:
  refreshInterval: 1h
  secretStoreRef:
    kind: ClusterSecretStore
    name: vault-backend  # or aws-secrets-manager, gcp-secret-manager
  target:
    name: algotrading-secrets
    creationPolicy: Owner
  data:
    # Database credentials
    - secretKey: database-url
      remoteRef:
        key: algotrading/production/database
        property: url
    
    # JWT secret
    - secretKey: jwt-secret
      remoteRef:
        key: algotrading/production/jwt
        property: secret
    
    # Admin credentials
    - secretKey: admin-username
      remoteRef:
        key: algotrading/production/admin
        property: username
    
    - secretKey: admin-password
      remoteRef:
        key: algotrading/production/admin
        property: password
```

### Alpaca Broker Secrets

```yaml
# k8s/external-secret-alpaca.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: alpaca-external-secrets
  namespace: algotrading
spec:
  refreshInterval: 1h
  secretStoreRef:
    kind: ClusterSecretStore
    name: vault-backend
  target:
    name: alpaca-secrets
    creationPolicy: Owner
  data:
    - secretKey: api-key
      remoteRef:
        key: algotrading/production/alpaca
        property: api-key
    
    - secretKey: secret-key
      remoteRef:
        key: algotrading/production/alpaca
        property: secret-key
    
    - secretKey: api-key-id
      remoteRef:
        key: algotrading/production/alpaca
        property: api-key-id
    
    - secretKey: api-secret-key
      remoteRef:
        key: algotrading/production/alpaca
        property: api-secret-key
```

## Populating Secrets in the Backend

### HashiCorp Vault

```bash
# Enable KV secrets engine
vault secrets enable -path=secret kv-v2

# Store database credentials
vault kv put secret/algotrading/production/database \
  url="postgresql://user:pass@db.example.com:5432/algotrading"

# Store JWT secret
vault kv put secret/algotrading/production/jwt \
  secret="$(openssl rand -base64 48)"

# Store admin credentials
vault kv put secret/algotrading/production/admin \
  username="admin" \
  password="$(openssl rand -base64 16)"

# Store Alpaca credentials
vault kv put secret/algotrading/production/alpaca \
  api-key="AKXXXXXXXXXXXXXXXXXX" \
  secret-key="XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX" \
  api-key-id="AKXXXXXXXXXXXXXXXXXX" \
  api-secret-key="XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
```

### AWS Secrets Manager

```bash
# Create database secret
aws secretsmanager create-secret \
  --name algotrading/production/database \
  --secret-string '{"url":"postgresql://user:pass@db.example.com:5432/algotrading"}'

# Create JWT secret
aws secretsmanager create-secret \
  --name algotrading/production/jwt \
  --secret-string "{\"secret\":\"$(openssl rand -base64 48)\"}"
```

## Verification

### Check ExternalSecret Status

```bash
# Check if external secrets are synced
kubectl -n algotrading get externalsecrets
kubectl -n algotrading describe externalsecret algotrading-external-secrets

# Verify the Kubernetes secret was created
kubectl -n algotrading get secret algotrading-secrets
```

### Troubleshooting

```bash
# Check ESO operator logs
kubectl -n external-secrets logs -l app.kubernetes.io/name=external-secrets

# Check sync events
kubectl -n algotrading get events --field-selector reason=Updated

# Describe external secret for errors
kubectl -n algotrading describe externalsecret algotrading-external-secrets
```

## Secret Rotation

ESO automatically refreshes secrets based on `refreshInterval`. For immediate rotation:

```bash
# Force refresh
kubectl -n algotrading annotate externalsecret algotrading-external-secrets \
  force-sync=$(date +%s) --overwrite
```

## Migration from Static Secrets

1. Create secrets in your backend (Vault/AWS/GCP)
2. Create the ClusterSecretStore
3. Create ExternalSecret resources
4. Delete the static `k8s/secrets.yaml` from deployments
5. Update Kustomization to exclude static secrets

## Security Best Practices

1. **Least Privilege**: Grant minimal permissions to ESO service accounts
2. **Audit Logging**: Enable audit logs on your secrets backend
3. **Rotation Policy**: Set appropriate `refreshInterval` (1h recommended)
4. **Network Policies**: Restrict ESO's network access to only the secrets backend
5. **RBAC**: Limit who can create/modify ExternalSecret resources

## Related Documentation

- [External Secrets Operator Docs](https://external-secrets.io/)
- [HashiCorp Vault](https://www.vaultproject.io/docs)
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/)
- [k8s/secrets.yaml](../../k8s/secrets.yaml) - Base secrets template
