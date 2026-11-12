ui = false
disable_mlock = true
api_addr = "http://openbao:8200"
storage "file" {
  path = "/bao/data"
}
# Isolated local test network only. Production requires TLS and durable unseal.
listener "tcp" {
  address = "0.0.0.0:8200"
  tls_disable = true
}