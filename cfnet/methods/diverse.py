# AUTOGENERATED! DO NOT EDIT! File to edit: ../../nbs/05b_methods.diverse.ipynb.

# %% auto 0
__all__ = ['DiverseCFConfig', 'DiverseCF']

# %% ../../nbs/05b_methods.diverse.ipynb 3
from ..import_essentials import *
from .base import BaseCFModule
from ..data import TabularDataModule
from cfnet.utils import (
    check_cat_info,
    validate_configs,
    dist,
    grad_update,
)

# %% ../../nbs/05b_methods.diverse.ipynb 4
def hinge_loss(input: jnp.DeviceArray, target: jnp.DeviceArray):
    """
    reference:
    - https://github.com/interpretml/DiCE/blob/a772c8d4fcd88d1cab7f2e02b0bcc045dc0e2eab/dice_ml/explainer_interfaces/dice_pytorch.py#L196-L202
    - https://en.wikipedia.org/wiki/Hinge_loss
    """
    input = jnp.log((jnp.abs(input - 1e-6) / (1 - jnp.abs(input - 1e-6))))
    all_ones = jnp.ones_like(target)
    target = 2 * target - all_ones
    loss = all_ones - target * input
    loss = jax.nn.relu(loss)
    return jnp.linalg.norm(loss)


# %% ../../nbs/05b_methods.diverse.ipynb 5
def l1_mean(X, cfs):
    x_mean = jnp.mean(jnp.abs(X))
    l1_loss = jnp.mean(jnp.abs(X - cfs))
    return l1_loss / x_mean


# %% ../../nbs/05b_methods.diverse.ipynb 6
def dpp_style(cf: jnp.DeviceArray, n_cfs: int):
    det_entries = jnp.ones((n_cfs, n_cfs))
    for i in range(n_cfs):
        for j in range(n_cfs):
            det_entries.at[i, j].set(dist(cf[i], cf[j], ord=1))

    det_entries = 1.0 / (1.0 + det_entries)
    det_entries += jnp.eye(n_cfs) * 0.0001
    return jnp.linalg.det(det_entries)


# %% ../../nbs/05b_methods.diverse.ipynb 7
def _compute_regularization_loss(cfs, cat_idx, cat_arrays, n_cfs):
    # cat_idx = len(self.model.continous_cols)
    regularization_loss = 0.0
    for i in range(n_cfs):
        for col in cat_arrays:
            cat_idx_end = cat_idx + len(col)
            regularization_loss += jnp.power(
                (jnp.sum(cfs[i][cat_idx:cat_idx_end]) - 1.0), 2
            )
    return regularization_loss


# %% ../../nbs/05b_methods.diverse.ipynb 8
def _diverse_cf(
    x: jnp.DeviceArray,  # `x` shape: (k,), where `k` is the number of features
    pred_fn: Callable[[jnp.DeviceArray], jnp.DeviceArray],  # y = pred_fn(x)
    n_cfs: int,
    n_steps: int,
    lr: float,  # learning rate for each `cf` optimization step
    lambda_: float,  #  loss = validity_loss + lambda_params * cost
    key: jax.random.PRNGKey,
    projection_fn: Callable,
    regularization_fn: Callable
) -> jnp.DeviceArray:  # return `cf` shape: (k,)
    def loss_fn_1(cf_y: jnp.DeviceArray, y_prime: jnp.DeviceArray):
        return jnp.mean(hinge_loss(input=cf_y, target=y_prime))

    def loss_fn_2(x: jnp.DeviceArray, cf: jnp.DeviceArray):
        return jnp.mean(jnp.abs(cf - x))

    def loss_fn_3(cfs: jnp.DeviceArray, n_cfs: int):
        return dpp_style(cfs, n_cfs)

    def loss_fn_4(x: jnp.DeviceArray, cfs: jnp.DeviceArray):
        # return _compute_regularization_loss(cfs, cat_idx, cat_arrays, n_cfs)
        reg_loss = 0.
        for i in range(n_cfs):
            reg_loss += regularization_fn(x, cfs[i])
        return reg_loss

    def loss_fn(
        cf: jnp.DeviceArray,  # `cf` shape: (k, n_cfs)
        x: jnp.DeviceArray,  # `x` shape: (k, 1)
        pred_fn: Callable[[jnp.DeviceArray], jnp.DeviceArray],
    ):
        y_pred = pred_fn(x)
        y_prime = 1.0 - y_pred
        cf_y = pred_fn(cf)

        loss_1 = loss_fn_1(cf_y, y_prime)
        loss_2 = loss_fn_2(x, cf)
        loss_3 = loss_fn_3(cf, n_cfs)
        loss_4 = loss_fn_4(x, cfs)
        return loss_1 + loss_2 + loss_3 + loss_4

    @jax.jit
    def gen_cf_step(
        x: jnp.DeviceArray, cf: jnp.DeviceArray, opt_state: optax.OptState
    ) -> Tuple[jnp.DeviceArray, optax.OptState]:
        cf_grads = jax.grad(loss_fn)(cf, x, pred_fn)
        cf, opt_state = grad_update(cf_grads, cf, opt_state, opt)
        cf = jnp.clip(cf, 0.0, 1.0)
        return cf, opt_state

    x_size = x.shape
    if len(x_size) > 1 and x_size[0] != 1:
        raise ValueError(
            f"""Invalid Input Shape: Require `x.shape` = (1, k) or (k, ),
but got `x.shape` = {x.shape}. This method expects a single input instance."""
        )
    if len(x_size) == 1:
        x = x.reshape(1, -1)
    cfs = jax.random.normal(key, shape=(n_cfs, x.shape[-1]))
    opt = optax.rmsprop(lr)
    opt_state = opt.init(cfs)
    for _ in tqdm(range(n_steps)):
        cfs, opt_state = gen_cf_step(x, cfs, opt_state)
    cf = projection_fn(x, cfs[:1, :], hard=True)
    return cf.reshape(x_size)


# %% ../../nbs/05b_methods.diverse.ipynb 9
class DiverseCFConfig(BaseParser):
    n_cfs: int = 5
    n_steps: int = 1000
    lr: float = 0.01
    lambda_: float = 0.01  # loss = validity_loss + lambda_params * cost
    seed: int = 42

    @property
    def keys(self):
        return hk.PRNGSequence(self.seed)


# %% ../../nbs/05b_methods.diverse.ipynb 10
class DiverseCF(BaseCFModule):
    name = "DiverseCF"

    def __init__(
        self,
        configs: Union[Dict[str, Any], DiverseCFConfig] = None,
    ):
        if configs is None:
            configs = DiverseCFConfig()
        self.configs = validate_configs(configs, DiverseCFConfig)

    def generate_cf(
        self,
        x: jnp.ndarray,  # `x` shape: (k,), where `k` is the number of features
        pred_fn: Callable[[jnp.DeviceArray], jnp.DeviceArray],
    ) -> jnp.DeviceArray:
        return _diverse_cf(
            x=x,  # `x` shape: (k,), where `k` is the number of features
            pred_fn=pred_fn,  # y = pred_fn(x)
            n_cfs=self.configs.n_cfs,
            n_steps=self.configs.n_steps,
            lr=self.configs.lr,  # learning rate for each `cf` optimization step
            lambda_=self.configs.lambda_,  #  loss = validity_loss + lambda_params * cost
            key=next(self.configs.keys),
            projection_fn=self.data_module.apply_constraints,
            regularization_fn=self.data_module.apply_regularization
        )

    def generate_cfs(
        self,
        X: jnp.DeviceArray,  # `x` shape: (b, k), where `b` is batch size, `k` is the number of features
        pred_fn: Callable[[jnp.DeviceArray], jnp.DeviceArray],
        is_parallel: bool = False,
    ) -> jnp.DeviceArray:
        def _generate_cf(x: jnp.DeviceArray) -> jnp.ndarray:
            return self.generate_cf(x, pred_fn)

        return (
            jax.vmap(_generate_cf)(X) if not is_parallel else jax.pmap(_generate_cf)(X)
        )
