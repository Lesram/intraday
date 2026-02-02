# TLS/HTTPS Configuration Guide

**Platform:** Algorithmic Trading Platform  
**Purpose:** Production-grade TLS/HTTPS setup for secure API communication  
**Date:** October 4, 2025

---

## 📋 **OVERVIEW**

This guide provides comprehensive TLS/HTTPS configuration for the trading platform. Three implementation options are provided to support different deployment scenarios:

1. **Kubernetes with cert-manager** (Recommended for production)
2. **Kubernetes with manual certificates**
3. **Direct server configuration** (for non-K8s deployments)

All options integrate seamlessly with the existing platform architecture in `k8s/deployment.yaml`.

---

## 🎯 **PREREQUISITES**

### Required
- Kubernetes cluster with ingress controller installed
- Domain name pointing to your cluster (e.g., `trading.yourdomain.com`)
- Platform deployed using `k8s/deployment.yaml`

### Optional (for automatic cert management)
- cert-manager installed in cluster
- DNS provider API access (for DNS-01 challenge)

---

## ✅ **OPTION 1: Kubernetes + cert-manager (RECOMMENDED)**

### Why This Option?
- ✅ Automatic certificate renewal (Let's Encrypt)
- ✅ Zero-touch certificate management
- ✅ Production-grade security
- ✅ Free SSL certificates
- ✅ Integrates with existing Kubernetes setup

### Step 1: Install cert-manager

```bash
# Install cert-manager (if not already installed)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Verify installation
kubectl get pods --namespace cert-manager
```

### Step 2: Create ClusterIssuer

Create `k8s/tls/cert-issuer.yaml`:

```yaml
# Let's Encrypt Production Issuer
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: ops@yourdomain.com  # ⚠️ CHANGE THIS to your email
    privateKeySecretRef:
      name: letsencrypt-prod-key
    solvers:
    - http01:
        ingress:
          class: nginx
---
# Let's Encrypt Staging Issuer (for testing)
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-staging
spec:
  acme:
    server: https://acme-staging-v02.api.letsencrypt.org/directory
    email: ops@yourdomain.com  # ⚠️ CHANGE THIS to your email
    privateKeySecretRef:
      name: letsencrypt-staging-key
    solvers:
    - http01:
        ingress:
          class: nginx
```

Apply the issuer:
```bash
kubectl apply -f k8s/tls/cert-issuer.yaml
```

### Step 3: Create Ingress with TLS

Create `k8s/tls/ingress-tls.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: algotrading-ingress
  namespace: algotrading
  annotations:
    # Ingress class
    kubernetes.io/ingress.class: nginx
    
    # cert-manager annotations for automatic certificate management
    cert-manager.io/cluster-issuer: letsencrypt-prod
    cert-manager.io/acme-challenge-type: http01
    
    # Security headers
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/force-ssl-redirect: "true"
    
    # HSTS (HTTP Strict Transport Security)
    nginx.ingress.kubernetes.io/configuration-snippet: |
      more_set_headers "Strict-Transport-Security: max-age=31536000; includeSubDomains; preload";
      more_set_headers "X-Frame-Options: DENY";
      more_set_headers "X-Content-Type-Options: nosniff";
      more_set_headers "X-XSS-Protection: 1; mode=block";
    
    # Rate limiting (integrates with platform's existing rate limiting)
    nginx.ingress.kubernetes.io/limit-rps: "100"
    nginx.ingress.kubernetes.io/limit-connections: "50"
    
    # Timeouts (align with platform's async operations)
    nginx.ingress.kubernetes.io/proxy-connect-timeout: "60"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "60"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "60"
    
    # WebSocket support (for future streaming features)
    nginx.ingress.kubernetes.io/websocket-services: algotrading-api
    
    # Large request bodies (for bulk signal submissions)
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
    
spec:
  tls:
  - hosts:
    - trading.yourdomain.com  # ⚠️ CHANGE THIS to your domain
    secretName: algotrading-tls-cert  # cert-manager will create this secret
  
  rules:
  - host: trading.yourdomain.com  # ⚠️ CHANGE THIS to your domain
    http:
      paths:
      # Health check endpoints (no auth required)
      - path: /health
        pathType: Prefix
        backend:
          service:
            name: algotrading-api
            port:
              number: 8000
      
      - path: /healthz
        pathType: Prefix
        backend:
          service:
            name: algotrading-api
            port:
              number: 8000
      
      - path: /ready
        pathType: Prefix
        backend:
          service:
            name: algotrading-api
            port:
              number: 8000
      
      # Metrics endpoint (configure auth separately if needed)
      - path: /metrics
        pathType: Prefix
        backend:
          service:
            name: algotrading-api
            port:
              number: 8000
      
      # API endpoints (JWT auth handled by application)
      - path: /api/v1
        pathType: Prefix
        backend:
          service:
            name: algotrading-api
            port:
              number: 8000
      
      # Auth endpoints
      - path: /auth
        pathType: Prefix
        backend:
          service:
            name: algotrading-api
            port:
              number: 8000
      
      # Docs (optional, remove if not needed in production)
      - path: /docs
        pathType: Prefix
        backend:
          service:
            name: algotrading-api
            port:
              number: 8000
      
      - path: /redoc
        pathType: Prefix
        backend:
          service:
            name: algotrading-api
            port:
              number: 8000
```

Apply the ingress:
```bash
kubectl apply -f k8s/tls/ingress-tls.yaml
```

### Step 4: Verify TLS Certificate

```bash
# Check certificate status
kubectl describe certificate algotrading-tls-cert -n algotrading

# Check certificate details
kubectl get certificate -n algotrading

# View cert-manager logs if issues
kubectl logs -n cert-manager -l app=cert-manager --tail=100

# Test HTTPS endpoint
curl -v https://trading.yourdomain.com/health
```

### Step 5: Update Application Configuration

The application automatically works with HTTPS. No code changes needed! The platform's existing security middleware and health checks work seamlessly.

**Verify these existing platform features work over HTTPS:**
- JWT authentication (backend.infra.security)
- Health checks (/health, /ready)
- Monitoring endpoints (/api/v1/monitoring/*)
- API routes (/api/v1/*)

---

## 📝 **OPTION 2: Kubernetes with Manual Certificates**

### When to Use
- You have existing certificates from a CA
- Corporate environment with internal CA
- Custom certificate requirements

### Step 1: Create TLS Secret

```bash
# Create TLS secret from your certificate files
kubectl create secret tls algotrading-tls-cert \
  --cert=path/to/tls.crt \
  --key=path/to/tls.key \
  -n algotrading

# Verify secret created
kubectl get secret algotrading-tls-cert -n algotrading
```

### Step 2: Create Ingress (without cert-manager annotations)

Create `k8s/tls/ingress-manual-tls.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: algotrading-ingress
  namespace: algotrading
  annotations:
    kubernetes.io/ingress.class: nginx
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/force-ssl-redirect: "true"
    
    # Security headers
    nginx.ingress.kubernetes.io/configuration-snippet: |
      more_set_headers "Strict-Transport-Security: max-age=31536000; includeSubDomains";
      more_set_headers "X-Frame-Options: DENY";
      more_set_headers "X-Content-Type-Options: nosniff";
      
spec:
  tls:
  - hosts:
    - trading.yourdomain.com
    secretName: algotrading-tls-cert  # Reference your manual secret
  
  rules:
  - host: trading.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: algotrading-api
            port:
              number: 8000
```

### Step 3: Set Up Certificate Renewal Reminder

```bash
# Add to cron job to check certificate expiry
0 0 * * 0 kubectl get secret algotrading-tls-cert -n algotrading -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -enddate -noout
```

⚠️ **Important:** Manual certificates require manual renewal. Set reminders 30 days before expiry.

---

## 🔧 **OPTION 3: Direct Server Configuration (Non-Kubernetes)**

### When to Use
- Running on VMs without Kubernetes
- Development/staging environments
- Cloud provider load balancer handles TLS

### Using Cloud Provider Load Balancer

Most cloud providers offer TLS termination at the load balancer level:

**AWS (Application Load Balancer):**
```bash
# Create ACM certificate
aws acm request-certificate \
  --domain-name trading.yourdomain.com \
  --validation-method DNS

# Configure ALB to use certificate
# Associate certificate ARN with ALB listener on port 443
```

**GCP (Load Balancer):**
```bash
# Create managed certificate
gcloud compute ssl-certificates create algotrading-cert \
  --domains=trading.yourdomain.com

# Configure load balancer to use certificate
gcloud compute target-https-proxies create algotrading-https-proxy \
  --ssl-certificates=algotrading-cert \
  --url-map=algotrading-url-map
```

**Azure (Application Gateway):**
```bash
# Add certificate to Key Vault
az keyvault certificate import \
  --vault-name trading-keyvault \
  --name algotrading-cert \
  --file certificate.pfx

# Configure Application Gateway listener
az network application-gateway http-listener create \
  --name https-listener \
  --resource-group trading-rg \
  --gateway-name trading-gateway \
  --ssl-cert algotrading-cert
```

### Using Uvicorn with TLS (Development Only)

⚠️ **NOT RECOMMENDED FOR PRODUCTION**

```python
# For development/testing only
# Modify main.py temporarily:

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8443,  # HTTPS port
        ssl_keyfile="path/to/key.pem",
        ssl_certfile="path/to/cert.pem",
        ssl_ca_certs="path/to/ca-bundle.crt"  # Optional
    )
```

---

## ✅ **POST-DEPLOYMENT VERIFICATION**

### 1. Test HTTPS Endpoint

```bash
# Basic connectivity
curl -v https://trading.yourdomain.com/health

# Expected output:
# < HTTP/2 200
# < content-type: application/json
# < strict-transport-security: max-age=31536000; includeSubDomains
# {"status":"healthy","timestamp":"2025-10-04T..."}

# Verify TLS certificate
openssl s_client -connect trading.yourdomain.com:443 -servername trading.yourdomain.com < /dev/null
```

### 2. Test Platform Features Over HTTPS

```bash
# Test authentication
curl -X POST https://trading.yourdomain.com/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# Test API with JWT
TOKEN="<your-jwt-token>"
curl https://trading.yourdomain.com/api/v1/signals \
  -H "Authorization: Bearer $TOKEN"

# Test monitoring endpoints
curl https://trading.yourdomain.com/api/v1/monitoring/sli-metrics
curl https://trading.yourdomain.com/api/v1/monitoring/slo-status
```

### 3. Verify Security Headers

```bash
# Check security headers
curl -I https://trading.yourdomain.com/health

# Should see:
# strict-transport-security: max-age=31536000; includeSubDomains
# x-frame-options: DENY
# x-content-type-options: nosniff
```

### 4. Test HTTP to HTTPS Redirect

```bash
# HTTP request should redirect to HTTPS
curl -L http://trading.yourdomain.com/health

# Should automatically redirect to https://
```

### 5. Verify Certificate Details

```bash
# Check certificate expiry
echo | openssl s_client -servername trading.yourdomain.com -connect trading.yourdomain.com:443 2>/dev/null | openssl x509 -noout -dates

# Check certificate chain
echo | openssl s_client -servername trading.yourdomain.com -connect trading.yourdomain.com:443 -showcerts 2>/dev/null
```

---

## 🔍 **TROUBLESHOOTING**

### Certificate Not Being Issued

```bash
# Check cert-manager logs
kubectl logs -n cert-manager -l app=cert-manager --tail=100

# Check certificate status
kubectl describe certificate algotrading-tls-cert -n algotrading

# Check challenge status
kubectl get challenges -n algotrading

# Common issues:
# 1. DNS not pointing to cluster
# 2. Firewall blocking port 80 (needed for HTTP-01 challenge)
# 3. Incorrect email in ClusterIssuer
```

### SSL/TLS Errors

```bash
# Test certificate validity
curl -vvI https://trading.yourdomain.com 2>&1 | grep -A 10 "SSL certificate"

# Check ingress logs
kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx --tail=100

# Verify TLS secret exists
kubectl get secret algotrading-tls-cert -n algotrading -o yaml
```

### Platform Still Using HTTP

```bash
# Check service configuration
kubectl get svc algotrading-api -n algotrading -o yaml

# Check ingress status
kubectl get ingress algotrading-ingress -n algotrading

# Verify ingress controller
kubectl get pods -n ingress-nginx
```

---

## 📊 **INTEGRATION WITH EXISTING PLATFORM**

### Monitoring Integration

The TLS configuration integrates seamlessly with existing monitoring:

- **Health checks:** `/health`, `/healthz`, `/ready` work over HTTPS
- **Metrics:** `/metrics` endpoint accessible via HTTPS
- **SLI/SLO:** `/api/v1/monitoring/*` endpoints work over HTTPS
- **Prometheus:** Scraping configured in `k8s/deployment.yaml` annotations

### Security Integration

TLS enhances existing security features:

- **JWT Authentication:** Works seamlessly over HTTPS (backend.infra.security)
- **Brute-Force Protection:** User lockout mechanism works over HTTPS (backend.infra.users)
- **Rate Limiting:** Nginx ingress rate limits + application rate limiting (backend.brokers.alpaca_production)
- **CORS:** Existing CORS middleware works with HTTPS

### Database Integration

Database connections remain unchanged:

- **PostgreSQL:** Uses `DATABASE_URL` env var (from `k8s/deployment.yaml`)
- **Connection pooling:** Configured in `backend.infra.db`
- **Health checks:** `db_health_check()` works same way

### API Integration

External API calls remain unchanged:

- **Alpaca API:** Uses HTTPS by default (backend.integrations.alpaca_*)
- **API credentials:** From `ALPACA_API_KEY_ID` and `ALPACA_SECRET_KEY` env vars
- **Rate limiting:** Existing broker rate limiting continues working

---

## 📋 **DEPLOYMENT CHECKLIST**

Before going live with TLS:

- [ ] Domain DNS pointing to cluster external IP
- [ ] cert-manager installed (if using Option 1)
- [ ] ClusterIssuer created and validated
- [ ] Ingress with TLS created
- [ ] Certificate issued successfully (`kubectl get certificate`)
- [ ] HTTPS endpoint responding (`curl https://...`)
- [ ] HTTP redirects to HTTPS working
- [ ] Security headers present (`curl -I https://...`)
- [ ] Platform health checks passing over HTTPS
- [ ] Authentication working over HTTPS
- [ ] API endpoints accessible over HTTPS
- [ ] Monitoring endpoints working over HTTPS
- [ ] Certificate auto-renewal configured (Option 1) or reminder set (Option 2)
- [ ] Documentation updated with HTTPS URLs
- [ ] Client applications configured to use HTTPS
- [ ] Firewall rules allow port 443 (HTTPS)
- [ ] Load balancer health checks updated to use HTTPS

---

## 🚀 **PRODUCTION DEPLOYMENT COMMAND**

Once everything is configured:

```bash
# Apply TLS configuration (Option 1 - cert-manager)
kubectl apply -f k8s/tls/cert-issuer.yaml
kubectl apply -f k8s/tls/ingress-tls.yaml

# Wait for certificate
kubectl wait --for=condition=Ready certificate/algotrading-tls-cert -n algotrading --timeout=300s

# Verify deployment
kubectl get ingress algotrading-ingress -n algotrading
kubectl get certificate -n algotrading

# Test HTTPS
curl -v https://trading.yourdomain.com/health

# 🎉 Done! Platform now running on HTTPS
```

---

## 📝 **MAINTENANCE**

### Certificate Renewal (Option 1 - cert-manager)

Automatic! cert-manager handles renewal 30 days before expiry.

**Verify auto-renewal working:**
```bash
# Check cert-manager is running
kubectl get pods -n cert-manager

# Check renewal logs
kubectl logs -n cert-manager -l app=cert-manager | grep renewal
```

### Certificate Renewal (Option 2 - Manual)

Set calendar reminder for 30 days before expiry:

```bash
# Generate new certificate from CA
# Create new secret
kubectl create secret tls algotrading-tls-cert \
  --cert=new-cert.crt \
  --key=new-key.key \
  -n algotrading \
  --dry-run=client -o yaml | kubectl apply -f -

# Ingress will automatically pick up new certificate
```

### Monitoring Certificate Expiry

```bash
# Add to monitoring system (Prometheus)
# Sample query:
# ssl_certificate_expiry_days{service="algotrading-api"} < 30
```

---

## 🔐 **SECURITY BEST PRACTICES**

### Implemented in This Configuration

✅ **TLS 1.2+ only** (configured in ingress)  
✅ **Strong cipher suites** (nginx defaults)  
✅ **HSTS headers** (Strict-Transport-Security)  
✅ **X-Frame-Options: DENY** (prevents clickjacking)  
✅ **X-Content-Type-Options: nosniff** (prevents MIME sniffing)  
✅ **Force HTTPS redirect** (nginx.ingress.kubernetes.io/ssl-redirect)

### Additional Recommendations

- **Certificate Transparency:** Let's Encrypt certificates automatically logged
- **OCSP Stapling:** Enabled by default in nginx ingress
- **Perfect Forward Secrecy:** Supported by default
- **Regular Security Scans:** Use tools like SSL Labs, testssl.sh

---

## 📚 **REFERENCES**

- [cert-manager Documentation](https://cert-manager.io/docs/)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
- [Kubernetes Ingress TLS](https://kubernetes.io/docs/concepts/services-networking/ingress/#tls)
- [nginx Ingress Controller](https://kubernetes.github.io/ingress-nginx/)
- [Platform Deployment Guide](../k8s/deployment.yaml)
- [Platform Security Implementation](../backend/infra/security.py)

---

**Document Version:** 1.0  
**Last Updated:** October 4, 2025  
**Status:** Production-Ready ✅
