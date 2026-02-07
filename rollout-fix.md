# Rollout stuck — diagnose and fix

## 1. See why pods aren’t ready

```bash
kubectl get pods -l app=cmprss-web -o wide
kubectl get pods -l app=cmprss-worker -o wide
```

Look at **STATUS** (Running, Pending, CrashLoopBackOff, ImagePullBackOff) and **READY** (e.g. 0/1).

## 2. Inspect the web pod (replace name if different)

```bash
kubectl describe pod -l app=cmprss-web | tail -30
```

Check **Events** at the bottom: ImagePullBackOff, CrashLoopBackOff, Readiness probe failed, etc.

## 3. Same for worker

```bash
kubectl describe pod -l app=cmprss-worker | tail -30
```

## 4. If new pods are **ImagePullBackOff** or **ErrImagePull**

Image pull is failing (registry auth or tag missing). Fix auth or use an image that exists, then:

```bash
kubectl delete pod -l app=cmprss-web
kubectl delete pod -l app=cmprss-worker
```

New pods will be created and will retry the pull.

## 5. If new pods are **CrashLoopBackOff**

App is exiting. Check logs:

```bash
kubectl logs -l app=cmprss-web --tail=50
kubectl logs -l app=cmprss-worker --tail=50
```

Fix the cause (config, missing env, etc.) and redeploy.

## 6. If old pods are stuck **Terminating**

Often due to a finalizer or the node not responding. Force delete (only if they’re really stuck):

```bash
kubectl get pods -l app=cmprss-web
kubectl delete pod <old-pod-name> -l app=cmprss-web --force --grace-period=0
```

(Same for worker if needed.) Then check rollout again.

## 7. If **progress deadline** is too short

Deployment might be fine but needs more time. Increase the deadline and retry:

```bash
kubectl patch deployment cmprss-web -p '{"spec":{"progressDeadlineSeconds":600}}'
kubectl patch deployment cmprss-worker -p '{"spec":{"progressDeadlineSeconds":600}}'
kubectl rollout status deployment/cmprss-web
kubectl rollout status deployment/cmprss-worker
```

## 8. Undo the image change (back to previous working revision)

If the last working state was before you set v17, undo so the deployment uses the previous image again:

```bash
kubectl rollout undo deployment/cmprss-web
kubectl rollout undo deployment/cmprss-worker
kubectl rollout status deployment/cmprss-web
kubectl rollout status deployment/cmprss-worker
```

Then run **step 1** again to confirm pods are Running and Ready.
