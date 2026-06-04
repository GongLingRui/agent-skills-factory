# 41. Nginx 配置

> 版本：v0.6 · 2026-05-06

---

## 主配置

```nginx
# /etc/nginx/conf.d/agent-factory.conf
upstream api_gateway {
    least_conn;
    server api-gateway-1:8000 weight=5;
    server api-gateway-2:8000 weight=5;
    server api-gateway-3:8000 weight=5;
    keepalive 32;
}

upstream widget {
    least_conn;
    server widget-1:3000;
    server widget-2:3000;
}

server {
    listen 443 ssl http2;
    server_name agent.company.com;

    # SSL
    ssl_certificate /etc/nginx/ssl/agent.company.com.crt;
    ssl_certificate_key /etc/nginx/ssl/agent.company.com.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Security Headers
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' wss:; frame-ancestors 'none';" always;

    # Access log with token masking
    access_log /var/log/nginx/agent-factory.access.log masked;

    # Rate limiting zones
    limit_req_zone $binary_remote_addr zone=ip:10m rate=100r/s;
    limit_req_zone $http_x_forwarded_for zone=per_ip:10m rate=30r/s;

    # Health check endpoint (no rate limit)
    location /health {
        proxy_pass http://api_gateway;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }

    # API routes
    location /api/ {
        limit_req zone=ip burst=50 nodelay;
        limit_req zone=per_ip burst=20 nodelay;

        proxy_pass http://api_gateway;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE support
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;

        # CORS
        add_header Access-Control-Allow-Origin "https://portal.company.com" always;
        add_header Access-Control-Allow-Credentials "true" always;
        add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Authorization, Content-Type, X-Trace-Id" always;

        if ($request_method = 'OPTIONS') {
            return 204;
        }
    }

    # Admin routes (stricter IP whitelist)
    location /admin/ {
        allow 10.0.0.0/8;
        allow 172.16.0.0/12;
        deny all;

        proxy_pass http://api_gateway;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Widget static assets
    location / {
        proxy_pass http://widget;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # Cache static assets
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
            expires 1d;
            add_header Cache-Control "public, immutable";
        }
    }

    # Error pages
    error_page 500 502 503 504 /50x.html;
    location = /50x.html {
        root /usr/share/nginx/html;
    }
}

# Log format with token masking
log_format masked '$remote_addr - $remote_user [$time_local] '
                  '"$request_method $masked_uri HTTP/$server_protocol" '
                  '$status $body_bytes_sent '
                  '"$http_referer" "$http_user_agent" '
                  'rt=$request_time uct="$upstream_connect_time" '
                  'uht="$upstream_header_time" urt="$upstream_response_time"';

# Map to mask token in query string
map $request_uri $masked_uri {
    default $request_uri;
    ~^(.*)[?&]token=[^&]+(.*)$ $1[MASKED]$2;
}
```

---

## 灰度发布 Ingress 配置

```nginx
# Canary 配置（通过 nginx ingress annotations 实现）
# 5% 流量路由到 canary
location /api/ {
    set $backend "stable";

    # 约 5% canary（$request_id 为 16 进制，前两位匹配概率 12/256 ≈ 4.7%）
    if ($cookie_canary = "always") {
        set $backend "canary";
    }
    if ($request_id ~ "^0[0-9a-b]") {
        set $backend "canary";
    }

    proxy_pass http://agent-factory-$backend;
}
```

---

## 与现有文档的衔接

- **API Gateway 设计** → [06-api-gateway.md](06-api-gateway.md)
- **部署拓扑** → [18-deployment-ops.md](18-deployment-ops.md)
- **安全策略** → [12-security-audit.md](12-security-audit.md)
- **CI/CD 灰度发布** → [28-cicd.md](28-cicd.md)
