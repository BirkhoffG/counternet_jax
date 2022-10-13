# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/01_datasets.ipynb.

# %% auto 0
__all__ = ['Dataset', 'DataLoader', 'find_imutable_idx_list', 'DataModuleConfigs', 'TabularDataModule']

# %% ../nbs/01_datasets.ipynb 3
from .import_essentials import *
from sklearn.preprocessing import StandardScaler,MinMaxScaler,OneHotEncoder

# %% ../nbs/01_datasets.ipynb 4
class Dataset:
    def __init__(self, X, y):
        self.X = X
        self.y = y
        assert self.X.shape[0] == self.y.shape[0]

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]

# %% ../nbs/01_datasets.ipynb 5
# copy from https://jax.readthedocs.io/en/latest/notebooks/Neural_Network_and_Data_Loading.html#data-loading-with-pytorch
def _numpy_collate(batch):
  if isinstance(batch[0], np.ndarray):
    return np.stack(batch)
  elif isinstance(batch[0], (tuple,list)):
    transposed = zip(*batch)
    return [_numpy_collate(samples) for samples in transposed]
  else:
    return np.array(batch)

class DataLoader:
    def __init__(self,dataset, batch_size=1,
                shuffle=False, sampler=None,
                batch_sampler=None, num_workers=0,collate_fn=_numpy_collate,
                pin_memory=False, drop_last=False,
                timeout=0, worker_init_fn=None):
        # Attributes from pytorch data loader
        self.dataset = dataset
        self.batch_size = batch_size
        self.shuffle=shuffle
        self.sampler=sampler
        self.batch_sampler=batch_sampler
        self.num_workers=num_workers
        self.collate_fn=collate_fn
        self.pin_memory=pin_memory
        self.drop_last=drop_last
        self.timeout=timeout
        self.worker_init_fn=worker_init_fn

        self.dataLen = len(dataset)
        self.keySeq = hk.PRNGSequence(42)
        self.keySeq.reserve(len(self))
        self.key = next(self.keySeq)
        self.indices = jax.numpy.arange(self.dataLen)
        self.pose = 0
    def __len__(self):
        batches = -(len(self.dataset) // -self.batch_size)
        return batches

    def __next__(self):
        if self.pose <= self.dataLen:
            if self.shuffle:
                self.key = next(self.keySeq)
                self.indices = jax.random.permutation(self.key, self.indices)
            batch_data = [self.dataset[i] for i in self.indices[:self.batch_size]]
            self.indices = self.indices[self.batch_size:]
            self.pose += self.batch_size
            return self.collate_fn(batch_data)
        else:
            self.pose = 0
            self.indices = jax.numpy.arange(self.dataLen)
            raise StopIteration

    def __iter__(self):
        return self



def find_imutable_idx_list(
    imutable_col_names: List[str],
    discrete_col_names: List[str],
    continuous_col_names: List[str],
    cat_arrays: List[List[str]]
) -> List[int]:
    imutable_idx_list = []
    for idx, col_name in enumerate(continuous_col_names):
        if col_name in imutable_col_names:
            imutable_idx_list.append(idx)

    cat_idx = len(continuous_col_names)

    for i, (col_name, cols) in enumerate(zip(discrete_col_names, cat_arrays)):
        cat_end_idx = cat_idx + len(cols)
        if col_name in imutable_col_names:
            imutable_idx_list += list(range(cat_idx, cat_end_idx))
        cat_idx = cat_end_idx
    return imutable_idx_list

# %% ../nbs/01_datasets.ipynb 6
class DataModuleConfigs(BaseParser):
    batch_size: int
    discret_cols: List[str] = []
    continous_cols: List[str] = []
    imutable_cols: List[str] = []
    normalizer: Optional[Any] = None
    encoder: Optional[Any] = None
    sample_frac: Optional[float] = None

# %% ../nbs/01_datasets.ipynb 7
class TabularDataModule:
    discret_cols: List[str] = []
    continous_cols: List[str] = []
    imutable_cols: List[str] = []
    normalizer: Optional[Any] = None
    encoder: Optional[OneHotEncoder] = None
    data: Optional[pd.DataFrame] = None
    sample_frac: Optional[float] = None
    batch_size: int = 128
    data_name: str = ""

    def __init__(self, data_configs: Dict):
        # read data
        self.data = pd.read_csv(Path(data_configs['data_dir']))
        # update configs
        self._update_configs(data_configs)
        self.check_cols()
        # update cat_idx
        self.cat_idx = len(self.continous_cols)
        # prepare data
        self.prepare_data()

    def check_cols(self):
        self.data = self.data.astype({col: np.float for col in self.continous_cols})
        # check imutable cols
        cols = self.continous_cols + self.discret_cols
        for col in self.imutable_cols:
            assert col in cols, \
                f"imutable_cols=[{col}] is not specified in `continous_cols` or `discret_cols`."

    def _update_configs(self, configs):
        for k, v in configs.items():
            setattr(self, k, v)

    def prepare_data(self):
        def split_x_and_y(data: pd.DataFrame):
            X = data[data.columns[:-1]]
            y = data[[data.columns[-1]]]
            return X, y

        X, y = split_x_and_y(self.data)

        # preprocessing
        if self.normalizer:
            X_cont = self.normalizer.transform(X[self.continous_cols])
        else:
            self.normalizer = MinMaxScaler()
            X_cont = self.normalizer.fit_transform(
                X[self.continous_cols]) if self.continous_cols else np.array([[] for _ in range(len(X))])

        if self.encoder:
            X_cat = self.encoder.transform(X[self.discret_cols])
        else:
            self.encoder = OneHotEncoder(sparse=False)
            X_cat = self.encoder.fit_transform(
                X[self.discret_cols]) if self.discret_cols else np.array([[] for _ in range(len(X))])
        X = np.concatenate((X_cont, X_cat), axis=1)
        # get categorical arrays
        self.cat_arrays = self.encoder.categories_ if self.discret_cols else []
        self.imutable_idx_list = find_imutable_idx_list(
            imutable_col_names=self.imutable_cols,
            discrete_col_names=self.discret_cols,
            continuous_col_names=self.continous_cols,
            cat_arrays=self.cat_arrays
        )

        # prepare train & test
        train_test_tuple = train_test_split(X, y.to_numpy(), shuffle=False)
        train_X, test_X, train_y, test_y = map(lambda x: x.astype(jnp.float32), train_test_tuple)
        if self.sample_frac:
            train_size = int(len(train_X) * self.sample_frac)
            train_X, train_y = train_X[:train_size], train_y[:train_size]
        self.train_dataset = Dataset(train_X, train_y)
        self.val_dataset = Dataset(test_X, test_y)
        self.test_dataset = self.val_dataset

    def train_dataloader(self):
        return DataLoader(self.train_dataset, batch_size=self.batch_size,
                          pin_memory=True, shuffle=True, num_workers=0)

    def val_dataloader(self):
        return DataLoader(self.val_dataset, batch_size=self.batch_size * 4,
                          pin_memory=True, shuffle=False, num_workers=0)

    def test_dataloader(self):
        return DataLoader(self.val_dataset, batch_size=self.batch_size,
                          pin_memory=True, shuffle=False, num_workers=0)

    def get_sample_X(self, frac: Optional[float]=None):
        if frac is None:
            frac = 0.1
        train_X, train_y = self.train_dataset[:]
        train_size = int(len(train_X) * frac)
        return train_X[:train_size]
