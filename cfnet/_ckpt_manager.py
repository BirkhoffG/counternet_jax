# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/04b_ckpt_manager.ipynb.

# %% auto 0
__all__ = ['save_checkpoint', 'load_checkpoint', 'CheckpointManager']

# %% ../nbs/04b_ckpt_manager.ipynb 3
from .import_essentials import *
from collections import OrderedDict

# %% ../nbs/04b_ckpt_manager.ipynb 4
# https://github.com/deepmind/dm-haiku/issues/18#issuecomment-981814403
def save_checkpoint(state, ckpt_dir: Path):
    with open(os.path.join(ckpt_dir, "params.npy"), "wb") as f:
        for x in jax.tree_leaves(state):
            np.save(f, x, allow_pickle=False)

    tree_struct = jax.tree_map(lambda t: 0, state)
    with open(os.path.join(ckpt_dir, "tree.pkl"), "wb") as f:
        pickle.dump(tree_struct, f)

def load_checkpoint(ckpt_dir: Path):
    with open(os.path.join(ckpt_dir, "tree.pkl"), "rb") as f:
        tree_struct = pickle.load(f)

    leaves, treedef = jax.tree_flatten(tree_struct)
    with open(os.path.join(ckpt_dir, "params.npy"), "rb") as f:
        flat_state = [np.load(f) for _ in leaves]

    return jax.tree_unflatten(treedef, flat_state)

# %% ../nbs/04b_ckpt_manager.ipynb 5
class CheckpointManager:
    def __init__(self,
                 log_dir: Union[Path, str],
                 monitor_metrics: Optional[str],
                 max_n_checkpoints: int = 3):
        self.log_dir = Path(log_dir)
        self.monitor_metrics = monitor_metrics
        self.max_n_checkpoints = max_n_checkpoints
        self.checkpoints = OrderedDict()
        self.n_checkpoints = 0
        if self.monitor_metrics is None:
            warnings.warn("`monitor_metrics` is not specified in `CheckpointManager`. No checkpoints will be stored.")

    # update checkpoints based on monitor_metrics
    def update_checkpoints(self,
                           params: hk.Params,
                           opt_state: optax.OptState,
                           epoch_logs: Dict[str, float],
                           epochs: int,
                           steps: Optional[int] = None):
        if self.monitor_metrics is None:
            return
        if self.monitor_metrics not in epoch_logs:
            raise ValueError("The monitor_metrics ({}) is not appropriately configured.".format(self.monitor_metrics))
        metric = float(epoch_logs[self.monitor_metrics])
        if steps:
            ckpt_name = f'epoch={epochs}_step={steps}'
        else:
            ckpt_name = f'epoch={epochs}'

        if self.n_checkpoints < self.max_n_checkpoints:
            self.checkpoints[metric] = ckpt_name
            self.save_net_opt(params, opt_state, ckpt_name)
            self.n_checkpoints += 1
        else:
            old_metric, old_ckpt_name = self.checkpoints.popitem(last=True)
            if metric < old_metric:
                self.checkpoints[metric] = ckpt_name
                self.save_net_opt(params, opt_state, ckpt_name)
                self.delete_net_opt(old_ckpt_name)
            else:
                self.checkpoints[old_metric] = old_ckpt_name

        self.checkpoints = OrderedDict(
            sorted(self.checkpoints.items(), key=lambda x: x[0]))

    def save_net_opt(self, params, opt_state, ckpt_name: str):
        ckpt_dir = self.log_dir / f'{ckpt_name}'
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        model_ckpt_dir = ckpt_dir / 'model'
        opt_ckpt_dir = ckpt_dir / 'opt'
        # create dirs for storing states of model and optimizer
        model_ckpt_dir.mkdir(parents=True, exist_ok=True)
        opt_ckpt_dir.mkdir(parents=True, exist_ok=True)
        # save model and optimizer states
        save_checkpoint(params, model_ckpt_dir)
        save_checkpoint(opt_state, opt_ckpt_dir)

    def delete_net_opt(self, ckpt_name: str):
        ckpt_dir = self.log_dir / f'{ckpt_name}'
        shutil.rmtree(ckpt_dir)

    # deprecated
    def load_net_opt(self, ckpt_name: str):
        ckpt_dir = self.log_dir / f'{ckpt_name}'
        model_ckpt_dir = ckpt_dir / 'model'
        opt_ckpt_dir = ckpt_dir / 'opt'
        # load model and optimizer states
        params = load_checkpoint(model_ckpt_dir)
        opt_state = load_checkpoint(opt_ckpt_dir)
        return params, opt_state
