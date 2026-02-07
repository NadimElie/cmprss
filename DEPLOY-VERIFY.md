# Deploy and verify — copy each block in order

---

## 0. If v17 image doesn’t exist (build failed): roll back to v16

```bash
kubectl set image deployment/cmprss-web web=docker.io/nadimelie/cmprss:v16
kubectl set image deployment/cmprss-worker worker=docker.io/nadimelie/cmprss:v16
kubectl rollout status deployment/cmprss-web
kubectl rollout status deployment/cmprss-worker
```

---

## 1. Confirm source has the changes

```bash
cd /home/nad/cmprss
grep -n "jobId && String(jobId)" templates/index.html
grep -n "action=download" main.py
grep -n "cmprss-build:" templates/index.html
```

---

## 2. Build image

The Dockerfile uses ftp.us.debian.org by default (to avoid timeouts to deb.debian.org). If that still times out, use --network=host.

```bash
cd /home/nad/cmprss
docker build -t docker.io/nadimelie/cmprss:v17 .
```

If apt still times out, use host network:

```bash
cd /home/nad/cmprss
docker build --network=host -t docker.io/nadimelie/cmprss:v17 .
```

To try another mirror:

```bash
docker build --build-arg DEBIAN_MIRROR=ftp.debian.org -t docker.io/nadimelie/cmprss:v17 .
```

Check image:

```bash
docker images docker.io/nadimelie/cmprss:v17
```

---

## 3. Push image

```bash
docker push docker.io/nadimelie/cmprss:v17
```

---

## 4. Update k3s and wait for rollout

```bash
kubectl set image deployment/cmprss-web web=docker.io/nadimelie/cmprss:v17
kubectl set image deployment/cmprss-worker worker=docker.io/nadimelie/cmprss:v17
kubectl rollout status deployment/cmprss-web
kubectl rollout status deployment/cmprss-worker
```

---

## 5. Confirm pods use new image

```bash
kubectl get pods -l app=cmprss-web
kubectl get pods -l app=cmprss-worker
kubectl get pods -l app=cmprss-web -o jsonpath='{.items[0].spec.containers[0].image}'
echo
kubectl get pods -l app=cmprss-worker -o jsonpath='{.items[0].spec.containers[0].image}'
echo
```

---

## 6. Browser check

View Page Source (Ctrl+U), search for: `cmprss-build: v17`

---

## Optional: bump version in YAML

```bash
cd /home/nad/cmprss
sed -i 's/cmprss:v16/cmprss:v17/g' web.yaml worker.yaml
```
