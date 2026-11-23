"""One fixed movement-only affine calibration, identity-prior ridge; no hyperparameter search."""
import numpy as np

def fit(x,y):
    x=np.asarray(x,dtype=np.float64);y=np.asarray(y,dtype=np.float64)
    if x.ndim!=2 or x.shape!=y.shape or x.shape[0]<2 or x.shape[1]<1 or not np.isfinite(x).all() or not np.isfinite(y).all():raise ValueError('finite paired training scores required')
    n,d=x.shape;mean=x.mean(axis=0);std=np.maximum(x.std(axis=0),1e-6)
    z=(x-mean)/std;residual=y-x;offset=residual.mean(axis=0)
    # Fixed regularization: one unit of normalized squared coefficient penalty
    # per training row. No dev/heldout labels influence this choice or the fit.
    a=np.linalg.solve(z.T@z+n*np.eye(d),z.T@(residual-offset))
    w=np.eye(d)+a.T/std[np.newaxis,:];b=offset-(mean/std)@a
    if not np.isfinite(w).all() or not np.isfinite(b).all():raise ValueError('nonfinite calibrated weights')
    return w.astype('<f4'),b.astype('<f4')

def predict(x,w,b):
    x=np.asarray(x,dtype=np.float64);w=np.asarray(w,dtype=np.float64);b=np.asarray(b,dtype=np.float64)
    if x.ndim!=2 or w.shape!=(x.shape[1],x.shape[1]) or b.shape!=(x.shape[1],) or any(not np.isfinite(a).all() for a in (x,w,b)):raise ValueError('prediction dimensions/finite values')
    return x@w.T+b
