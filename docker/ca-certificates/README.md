# Extra trust anchors for the image build

This directory is **empty by default** and nothing needs to be put here for a
normal deployment.

It exists for networks that intercept TLS — corporate proxies, and consumer
antivirus products with an "HTTPS scanning" or "web shield" feature. On such a
network the TLS certificate your machine sees for `pypi.org` is not issued by a
public CA but re-signed by the interceptor. The Docker build runs in a container
that has never heard of that CA, so `pip install` fails while everything else on
the host works:

```text
SSLError(SSLCertVerificationError(1, '[SSL: CERTIFICATE_VERIFY_FAILED]
certificate verify failed: unable to get local issuer certificate'))
```

## Fix

Export your interceptor's root certificate in PEM form and drop it in here with
a `.crt` extension, then rebuild:

```bash
cp corporate-root.crt docker/ca-certificates/
docker compose build --no-cache bot
```

`.crt` files here are added to the image's trust store and used by `pip` for
that build only. They are **not** used by the running bot, and the default image
is unaffected when this directory is empty.

To find the certificate your network is presenting:

```bash
openssl s_client -connect pypi.org:443 -showcerts </dev/null 2>/dev/null \
  | openssl x509 -noout -issuer
```

If the issuer is not a public CA (Let's Encrypt, DigiCert, …), that is your
interceptor.

## Do not commit a certificate here

A CA certificate is specific to one network. Committing one makes the image
trust that authority everywhere it is ever built. Keep it local, or supply it
through your CI's secret store.

`.gitignore` in this directory therefore ignores `*.crt`.
