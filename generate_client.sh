# 安裝 OpenAPI Generator
npm install @openapitools/openapi-generator-cli -g

# 生成 Python 客戶端
openapi-generator-cli generate \
  -i openapi.json \
  -g python \
  -o ./clients/python \
  --additional-properties=packageName=fpg_client

# 生成 TypeScript 客戶端
openapi-generator-cli generate \
  -i openapi.json \
  -g typescript-fetch \
  -o ./clients/typescript

# 生成 Java 客戶端
openapi-generator-cli generate \
  -i openapi.json \
  -g java \
  -o ./clients/java \
  --additional-properties=groupId=com.fpg,artifactId=fpg-client 