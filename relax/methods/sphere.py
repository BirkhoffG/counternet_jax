# AUTOGENERATED! DO NOT EDIT! File to edit: ../../nbs/05e_sphere.ipynb.

# %% ../../nbs/05e_sphere.ipynb 3
from __future__ import annotations
from ..import_essentials import *
from .base import BaseCFModule
from ..utils import *

# %% auto 0
__all__ = ['hyper_sphere_coordindates', 'cat_sample', 'apply_immutable', 'GSConfig', 'GrowingSphere']

# %% ../../nbs/05e_sphere.ipynb 4
def hyper_sphere_coordindates(
    rng_key: jrand.PRNGKey, # Random number generator key
    x: Array, # Input instance with only continuous features. Shape: (1, n_features)
    n_samples: int, # Number of samples
    high: float, # Upper bound
    low: float, # Lower bound
    p_norm: int = 2 # Norm
):
    # Adapted from 
    # https://github.com/carla-recourse/CARLA/blob/24db00aa8616eb2faedea0d6edf6e307cee9d192/carla/recourse_methods/catalog/growing_spheres/library/gs_counterfactuals.py#L8
    key_1, key_2 = jrand.split(rng_key)
    delta = jrand.normal(key_1, shape=(n_samples, x.shape[-1]))
    dist = jrand.uniform(key_2, shape=(n_samples,)) * (high - low) + low
    norm_p = jnp.linalg.norm(delta, ord=p_norm, axis=1)
    d_norm = jnp.divide(dist, norm_p).reshape(-1, 1)  # rescale/normalize factor
    delta = jnp.multiply(delta, d_norm)
    candidates = x + delta

    return candidates

# %% ../../nbs/05e_sphere.ipynb 5
def cat_sample(
    rng_key: jrand.PRNGKey, # Random number generator key
    x: Array, # Input instance with only categorical features. Shape: (1, n_features)
    cat_arrays: List[List[str]],  # A list of a list of each categorical feature name
    n_samples: int,  # Number of samples to sample
): 
    def sample_categorical(rng_key: jrand.PRNGKey, col: np.ndarray):
        rng_key, subkey = jrand.split(rng_key)
        prob = jnp.ones(len(col)) / len(col)
        cat_sample = jax.nn.one_hot(
            jrand.categorical(rng_key, prob, shape=(n_samples,)), num_classes=len(col)
        )
        return rng_key, cat_sample
    
    candidates = []
    # We cannot use lax.scan here because cat_arrays is List[List[str]], not and can't ben an Array
    for col in cat_arrays:
        rng_key, cat_sample = sample_categorical(rng_key, col)
        candidates.append(cat_sample)
    candidates = jnp.concatenate(candidates, axis=1)
    return candidates

# %% ../../nbs/05e_sphere.ipynb 6
def _growing_spheres(
    rng_key: jrand.PRNGKey, # Random number generator key
    x: Array, # Input instance. Shape: (n_features)
    pred_fn: Callable, # Prediction function
    n_steps: int, # Number of steps
    n_samples: int,  # Number of samples to sample
    cat_idx: int, # Index of categorical features
    cat_arrays: List[List[str]],  # A list of a list of each categorical feature name
    step_size: float, # Step size
    p_norm: int, # Norm
    apply_fn: Callable # Apply immutable constraints
):
    
    def cond_fn(state):
        candidate_cf, count, _ = state
        # TODO: check candidate_cf is not empty
        
        return (jnp.all(jnp.isinf(candidate_cf))) & (count < n_steps)
        # return (not candidate_cf) & (count < n_steps)
    
    def body_fn(state):
        candidate_cf, count, rng_key = state
        rng_key, subkey_1, subkey_2 = jrand.split(rng_key, num=3)
        low, high = step_size * count, step_size * (count + 1)
        # Sample around x
        cont_candidates = hyper_sphere_coordindates(subkey_1, x[:, :cat_idx], n_samples, high, low, p_norm)
        cat_candidates = cat_sample(subkey_2, x[:, cat_idx:], cat_arrays, n_samples)
        candidates = jnp.concatenate([cont_candidates, cat_candidates], axis=1)
        # Apply immutable constraints
        candidates = apply_fn(x=x, cf=candidates)
        assert candidates.shape[1] == x.shape[1], f"candidates.shape = {candidates.shape}, x.shape = {x.shape}"

        # Calculate distance
        if p_norm == 1:
            dist = jnp.abs(candidates - x).sum(axis=1)
        elif p_norm == 2:
            dist = jnp.linalg.norm(candidates - x, ord=2, axis=1)
        else:
            raise ValueError("Only p_norm = 1 or 2 is supported")

        # Calculate counterfactual labels
        candidate_preds = pred_fn(candidates).round().reshape(-1)
        # print(candidate_preds != y_pred)
        indices = jnp.where(candidate_preds != y_pred, 1, 0).astype(bool)

        # candidates = candidates[indices]
        candidates = jnp.where(indices.reshape(-1, 1), candidates, jnp.empty_like(candidates))
        # dist = dist[indices]
        dist = jnp.where(indices.reshape(-1, 1), dist, jnp.empty_like(dist))

        if len(candidates) > 0:
            # Find the closest counterfactual
            closest_idx = dist.argmin()
            candidate_cf = candidates[closest_idx].reshape(1, -1)

        return candidate_cf, count + 1, rng_key
    

    x_size = x.shape
    if len(x_size) > 1 and x_size[0] != 1:
        raise ValueError(
            f"Invalid Input Shape: Require `x.shape` = (1, k) or (k, ), "
            f"but got `x.shape` = {x.shape}. This method expects a single input instance."
        )
    if len(x_size) == 1:
        x = x.reshape(1, -1)

    y_pred = pred_fn(x).round().reshape(-1)
    candidate_cf = jnp.ones_like(x) * jnp.inf
    count = 0
    state = (candidate_cf, count, rng_key)
    candidate_cf, _, _ = lax.while_loop(cond_fn, body_fn, state)
    return candidate_cf

# %% ../../nbs/05e_sphere.ipynb 7
def apply_immutable(x: Array, cf: Array, immutable_idx: List[int]):
    if immutable_idx is not None:
        cf = cf.at[:, immutable_idx].set(x[:, immutable_idx])
    return cf

# %% ../../nbs/05e_sphere.ipynb 8
class GSConfig(BaseParser):
    seed: int = 42
    n_steps: int = 10
    n_samples: int = 1000
    step_size: float = 0.05
    p_norm: int = 2
    

# %% ../../nbs/05e_sphere.ipynb 9
class GrowingSphere(BaseCFModule):
    name = "Growing Sphere"

    def __init__(
        self,
        configs: Dict | GSConfig = None
    ):
        if configs is None:
            configs = GSConfig()
        self.configs = validate_configs(configs, GSConfig)
    
    def generate_cf(
        self,
        x: Array,
        pred_fn: Callable,
    ):
        rng_key = jrand.PRNGKey(self.configs.seed)
        cat_idx = self.data_module.cat_idx
        apply_immutable_partial = partial(
            apply_immutable, immutable_idx=self.data_module._imutable_idx_list)
        cf = _growing_spheres(
            rng_key,
            x,
            pred_fn,
            self.configs.n_steps,
            self.configs.n_samples,
            cat_idx,
            self.data_module._cat_arrays,
            self.configs.step_size,
            self.configs.p_norm,
            apply_immutable_partial,
        )
        return cf
    
    def generate_cfs(
        self, 
        X: Array, 
        pred_fn: Callable = None
    ) -> jnp.ndarray:
        
        generate_cf_partial = partial(self.generate_cf, pred_fn=pred_fn)
        cfs = jax.vmap(generate_cf_partial)(X)
        return cfs