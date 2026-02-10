#!/bin/bash
# Setup script for Cedar authorization demo
# Creates a protected directory structure for testing authorization policies

set -e

echo "Setting up Cedar authorization demo environment..."

# Create protected directory structure
PROTECTED_DIR="$HOME/openclaw-demo-protected"

if [ -d "$PROTECTED_DIR" ]; then
    echo "⚠️  $PROTECTED_DIR already exists. Remove it? (y/n)"
    read -r response
    if [ "$response" = "y" ]; then
        rm -rf "$PROTECTED_DIR"
    else
        echo "Keeping existing directory. Exiting."
        exit 0
    fi
fi

# Create directory structure
mkdir -p "$PROTECTED_DIR/credentials"
mkdir -p "$PROTECTED_DIR/scripts"
mkdir -p "$PROTECTED_DIR/config"

# Create fake credentials that should be protected
cat > "$PROTECTED_DIR/credentials/api-keys.txt" << 'EOF'
# Fake API Keys - Demo Only
ANTHROPIC_API_KEY=sk-ant-demo-key-12345
AWS_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
EOF

cat > "$PROTECTED_DIR/credentials/database.conf" << 'EOF'
# Fake Database Credentials - Demo Only
DB_HOST=localhost
DB_USER=admin
DB_PASSWORD=super-secret-password
DB_NAME=production
EOF

# Create a dangerous script that should be protected
cat > "$PROTECTED_DIR/scripts/dangerous.sh" << 'EOF'
#!/bin/bash
# This is a fake dangerous script for demo purposes
echo "This script should not be executed by the agent!"
echo "It represents a potentially harmful operation."
EOF
chmod +x "$PROTECTED_DIR/scripts/dangerous.sh"

# Create a fake config file
cat > "$PROTECTED_DIR/config/production.yaml" << 'EOF'
# Fake Production Configuration - Demo Only
environment: production
api_endpoint: https://api.example.com
secret_token: fake-secret-token-12345
debug: false
EOF

# Create a README explaining the structure
cat > "$PROTECTED_DIR/README.md" << 'EOF'
# Protected Demo Directory

This directory is used for the Cedar authorization demo. It contains fake sensitive files
that Cedar policies will protect from unauthorized access.

## Structure

- `credentials/` - Fake API keys and database credentials (protected)
- `scripts/` - Scripts that should not be executed (protected)
- `config/` - Configuration files (protected)

## Cedar Policies

The following Cedar policies protect this directory:

- **policy-demo-deny-protected-reads**: Denies reading files in ~/openclaw-demo-protected/credentials/
- **policy-demo-deny-protected-writes**: Denies writing/editing files in ~/openclaw-demo-protected/
- **policy-demo-deny-protected-scripts**: Denies executing scripts in ~/openclaw-demo-protected/scripts/

## Testing

Try these commands to test the authorization:

1. **Denied - Read credentials:**
   ```
   Read the file ~/openclaw-demo-protected/credentials/api-keys.txt
   ```

2. **Denied - Write to protected directory:**
   ```
   Create a file at ~/openclaw-demo-protected/test.txt
   ```

3. **Denied - Execute protected script:**
   ```
   Run the script ~/openclaw-demo-protected/scripts/dangerous.sh
   ```

All of these should be denied by Cedar policies.
EOF

echo ""
echo "✓ Demo environment created successfully!"
echo ""
echo "Protected directory: $PROTECTED_DIR"
echo ""
echo "Contents:"
echo "  - credentials/api-keys.txt (fake API keys)"
echo "  - credentials/database.conf (fake DB credentials)"
echo "  - scripts/dangerous.sh (fake dangerous script)"
echo "  - config/production.yaml (fake config)"
echo ""
echo "Next steps:"
echo "1. Update Cedar policies to protect ~/openclaw-demo-protected/"
echo "2. Run demo examples to see authorization in action"
echo ""
