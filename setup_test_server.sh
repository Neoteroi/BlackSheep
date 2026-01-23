#!/bin/bash
# Setup script for HTTP/2 test server with self-signed certificates

set -e

echo "Setting up HTTP/2 Test Server"
echo "=============================="

# Create certs directory
mkdir -p certs

# Generate self-signed certificate
echo "Generating self-signed certificate..."
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout certs/server.key \
  -out certs/server.crt \
  -days 365 \
  -subj "/C=US/ST=Test/L=Test/O=Test/CN=localhost"

echo "Certificate generated!"

# Create nginx config for HTTP/2
cat > nginx-http2.conf << 'EOF'
events {
    worker_connections 1024;
}

http {
    # Logging
    access_log /dev/stdout;
    error_log /dev/stderr info;

    # HTTP/2 Server
    server {
        listen 443 ssl;
        http2 on;
        server_name localhost;

        # SSL Configuration
        ssl_certificate /etc/nginx/ssl/server.crt;
        ssl_certificate_key /etc/nginx/ssl/server.key;

        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;

        # Test endpoints
        location / {
            add_header Content-Type text/plain;
            return 200 "HTTP/2 Test Server\nProtocol: $server_protocol\nMethod: $request_method\nURI: $request_uri\nHost: $host\n";
        }

        location /get {
            add_header Content-Type application/json;
            return 200 '{"method":"GET","protocol":"$server_protocol","uri":"$request_uri","host":"$host"}';
        }

        location /post {
            add_header Content-Type application/json;
            return 200 '{"method":"POST","protocol":"$server_protocol","uri":"$request_uri","content_type":"$content_type"}';
        }

        location /headers {
            add_header Content-Type application/json;
            return 200 '{"user_agent":"$http_user_agent","headers":"$http_x_custom_header"}';
        }

        location /delay/2 {
            add_header Content-Type application/json;
            return 200 '{"delay":2,"protocol":"$server_protocol","note":"Use external tool for delays"}';
        }
    }
}
EOF

echo "Nginx config created!"

# Start nginx container
echo "Starting nginx HTTP/2 server..."
docker run --rm -d -p 8443:443 --name http2-server \
    -v $(pwd)/nginx-http2.conf:/etc/nginx/nginx.conf:$(whoami) \
    -v $(pwd)/certs:/etc/nginx/ssl:$(whoami) \
    nginx:alpine

echo ""
echo "HTTP/2 server is running on https://localhost:8443"
echo ""
echo "Test with: python test_local.py"
echo "Stop with: docker stop http2-server"
