# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/01_datasets.ipynb.

# %% ../nbs/01_datasets.ipynb 2
from __future__ import annotations
from .import_essentials import *
from sklearn.preprocessing import StandardScaler,MinMaxScaler,OneHotEncoder
from urllib.request import urlretrieve

# %% auto 0
__all__ = ['backend2dataloader', 'Dataset', 'BaseDataLoader', 'DataLoaderPytorch', 'DataLoaderJax', 'DataLoader',
           'find_imutable_idx_list', 'DataModuleConfigs', 'TabularDataModule']

# %% ../nbs/01_datasets.ipynb 3
try:
    import torch.utils.data as torch_data
except ModuleNotFoundError:
    torch_data = None

# %% ../nbs/01_datasets.ipynb 5
class Dataset:
    def __init__(self, X, y):
        self.X = X
        self.y = y
        assert self.X.shape[0] == self.y.shape[0]

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]

# %% ../nbs/01_datasets.ipynb 6
class BaseDataLoader(ABC):
    def __init__(
        self, 
        dataset,
        backend: str,
        *,
        batch_size: int = 1,  # batch size
        shuffle: bool = False,  # if true, dataloader shuffles before sampling each batch
        num_workers: int = 0,
        drop_last: bool = False,
        **kwargs
    ):
        pass 
    
    def __len__(self):
        raise NotImplementedError
    
    def __next__(self):
        raise NotImplementedError
    
    def __iter__(self):
        raise NotImplementedError

# %% ../nbs/01_datasets.ipynb 8
# copy from https://jax.readthedocs.io/en/latest/notebooks/Neural_Network_and_Data_Loading.html#data-loading-with-pytorch
def _numpy_collate(batch):
    if isinstance(batch[0], np.ndarray):
        return np.stack(batch)
    elif isinstance(batch[0], (tuple, list)):
        transposed = zip(*batch)
        return [_numpy_collate(samples) for samples in transposed]
    else:
        return np.array(batch)

def _convert_dataset_pytorch(dataset: Dataset):
    class DatasetPytorch(torch_data.Dataset):
        def __init__(self, dataset: Dataset): self.dataset = dataset
        def __len__(self): return len(self.dataset)
        def __getitem__(self, idx): return self.dataset[idx]
    
    return DatasetPytorch(dataset)

# %% ../nbs/01_datasets.ipynb 9
class DataLoaderPytorch(BaseDataLoader):
    def __init__(
        self, 
        dataset: Dataset,
        backend: str = 'pytorch', # positional argument
        *,
        batch_size: int = 1,  # batch size
        shuffle: bool = False,  # if true, dataloader shuffles before sampling each batch
        num_workers: int = 0,
        drop_last: bool = False,
        **kwargs
    ):
        if torch_data is None:
            raise ModuleNotFoundError("`pytorch` library needs to be installed. Try `pip install torch`."
            "Please refer to pytorch documentation for details: https://pytorch.org/get-started/.")
        
        dataset = _convert_dataset_pytorch(dataset)
        self.dataloader = torch_data.DataLoader(
            dataset, 
            batch_size=batch_size, 
            shuffle=shuffle, 
            num_workers=num_workers, 
            drop_last=drop_last,
            collate_fn=_numpy_collate,
            **kwargs
        ) 

    def __len__(self):
        return len(self.dataloader)

    def __next__(self):
        return next(self.dataloader)

    def __iter__(self):
        return self.dataloader.__iter__()

# %% ../nbs/01_datasets.ipynb 11
class DataLoaderJax(BaseDataLoader):
    def __init__(
        self, 
        dataset: Dataset,
        backend: str,
        *,
        batch_size: int = 1,  # batch size
        shuffle: bool = False,  # if true, dataloader shuffles before sampling each batch
        num_workers: int = 0,
        drop_last: bool = False,
        **kwargs
    ):
        # Attributes from pytorch data loader (implemented)
        self.dataset = dataset
        self.batch_size = batch_size
        self.shuffle = shuffle
        self.seed = 42 # TODO: maybe use a global seed or something in the future
        self.collate_fn = _numpy_collate
        self.drop_last = drop_last

        self.data_len: int = len(dataset)  # Length of the dataset
        self.key_seq: hk.PRNGSequence = hk.PRNGSequence(
            self.seed
        )  # random number sequence
        self.key_seq.reserve(
            len(self)
        )  # generate some random number as key based on the number of batches
        self.key = next(self.key_seq)  # obtain a random key from the sequence
        self.indices: jax.numpy.array = jax.numpy.arange(
            self.data_len
        )  # available indices in the dataset
        self.pose: int = 0  # record the current position in the dataset

    def __len__(self):
        if self.drop_last:
            batches = len(self.dataset) // self.batch_size  # get the floor of division
        else:
            batches = -(
                len(self.dataset) // -self.batch_size
            )  # get the ceil of division
        return batches

    def __next__(self):
        if self.pose <= self.data_len:
            if self.shuffle:
                self.key = next(self.key_seq)
                self.indices = jax.random.permutation(self.key, self.indices)
            batch_data = self.dataset[self.indices[: self.batch_size]]
            batch_data = list(map(tuple, zip(*batch_data)))
            self.indices = self.indices[self.batch_size :]
            if self.drop_last and len(self.indices) < self.batch_size:
                self.pose = 0
                self.indices = jax.numpy.arange(self.data_len)
                raise StopIteration
            self.pose += self.batch_size
            return self.collate_fn(batch_data)
        else:
            self.pose = 0
            self.indices = jax.numpy.arange(self.data_len)
            raise StopIteration

    def __iter__(self):
        return self

# %% ../nbs/01_datasets.ipynb 13
backend2dataloader = {
    'jax': DataLoaderJax,
    'pytorch': DataLoaderPytorch,
    'tensorflow': None,
    'merlin': None,
}

# %% ../nbs/01_datasets.ipynb 14
def _dispatch_datalaoder(backend: str):
    dataloader_backends = backend2dataloader.keys()
    if not backend in dataloader_backends:
        raise ValueError(f"backend=`{backend}` is an invalid backend for dataloader. "
            f"Should be one of {dataloader_backends}.")
    
    dataloader_cls = backend2dataloader[backend]
    if dataloader_cls is None:
        raise NotImplementedError(f'backend=`{backend}` is not supported yet.')
    return dataloader_cls


# %% ../nbs/01_datasets.ipynb 15
class DataLoader(BaseDataLoader):
    def __init__(
        self,
        dataset,
        backend,
        *,
        batch_size: int = 1,  # batch size
        shuffle: bool = False,  # if true, dataloader shuffles before sampling each batch
        num_workers: int = 0,
        drop_last: bool = False,
        **kwargs
    ):
        self.__class__ = _dispatch_datalaoder(backend)
        self.__init__(
            dataset=dataset, 
            backend=backend, 
            batch_size=batch_size, 
            shuffle=shuffle, 
            num_workers=num_workers,
            drop_last=drop_last,
            **kwargs
        )

# %% ../nbs/01_datasets.ipynb 24
def find_imutable_idx_list(
    imutable_col_names: List[str],
    discrete_col_names: List[str],
    continuous_col_names: List[str],
    cat_arrays: List[List[str]],
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

# %% ../nbs/01_datasets.ipynb 25
def _data_name2configs(data_name: str):
    with open('../assets/configs/{}.json'.format(data_name)) as json_file:
        data = json.load(json_file)
        data_configs['data_name'] = data_name
        data_configs['discret_cols'] = data['discret_cols']
        data_configs['continous_cols'] = data['continous_cols']
        data_configs['imutable_cols'] = data.get('imutable_cols', [])
        data_configs['sample_frac'] = data.get('sample_frac', [])
        data_configs['normalizer'] = data.get('normalizer', [])
        data_configs['encoder'] = data.get('encoder', [])
        data_configs['data_dir'] = _download_data(data_name)
    return data_configs

def _download_data(data_name: str):
        url = 'https://github.com/BirkhoffG/cfnet/raw/master/assets/data/{}.csv'.format(data_name)
        path = Path(os.getcwd())
        path = path / "cf_data"
        if not path.exists():
            os.makedirs(path)
        path = path / f'{data_name}.csv'
        if path.is_file():
            return path
        else:
            urlretrieve(url,path)
            return path

# %% ../nbs/01_datasets.ipynb 26
class DataModuleConfigs(BaseParser):
    batch_size: int
    discret_cols: List[str] = []
    continous_cols: List[str] = []
    imutable_cols: List[str] = []
    normalizer: Optional[Any] = None
    encoder: Optional[Any] = None
    sample_frac: Optional[float] = None
    backend: str = 'jax'

# %% ../nbs/01_datasets.ipynb 27
class TabularDataModule:
    discret_cols: List[str] = []
    continous_cols: List[str] = []
    imutable_cols: List[str] = []
    normalizer: Optional[Any] = None
    encoder: Optional[OneHotEncoder] = None
    data: Optional[pd.DataFrame] = None
    sample_frac: Optional[float] = None
    batch_size: int = 128
    backend: str = 'jax'
    data_name: str = ""

    def __init__(self, data_configs: dict | str = None):
        if isinstance(data_configs, str):
            data_configs = _data_name2configs(data_configs)
            self.data = pd.read_csv(Path(data_configs['data_dir']))
        elif isinstance(data_configs, dict):
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
            assert (
                 col in cols
             ), f"imutable_cols=[{col}] is not specified in `continous_cols` or `discret_cols`."

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
            X_cont = (
                 self.normalizer.fit_transform(X[self.continous_cols])
                 if self.continous_cols
                 else np.array([[] for _ in range(len(X))])
             )

        if self.encoder:
            X_cat = self.encoder.transform(X[self.discret_cols])
        else:
            self.encoder = OneHotEncoder(sparse=False)
            X_cat = (
                 self.encoder.fit_transform(X[self.discret_cols])
                 if self.discret_cols
                 else np.array([[] for _ in range(len(X))])
             )
        X = np.concatenate((X_cont, X_cat), axis=1)
        # get categorical arrays
        self.cat_arrays = self.encoder.categories_ if self.discret_cols else []
        self.imutable_idx_list = find_imutable_idx_list(
            imutable_col_names=self.imutable_cols,
            discrete_col_names=self.discret_cols,
            continuous_col_names=self.continous_cols,
            cat_arrays=self.cat_arrays,
        )

        # prepare train & test
        train_test_tuple = train_test_split(X, y.to_numpy(), shuffle=False)
        train_X, test_X, train_y, test_y = map(
             lambda x: x.astype(jnp.float32), train_test_tuple
         )
        if self.sample_frac:
            train_size = int(len(train_X) * self.sample_frac)
            train_X, train_y = train_X[:train_size], train_y[:train_size]
        self.train_dataset = Dataset(train_X, train_y)
        self.val_dataset = Dataset(test_X, test_y)
        self.test_dataset = self.val_dataset

    def train_dataloader(self, batch_size):
        return DataLoader(
             self.train_dataset,
             self.backend,
             batch_size=batch_size,
             shuffle=True,
             num_workers=0,
             drop_last=False
         )

    def val_dataloader(self, batch_size):
        return DataLoader(
             self.val_dataset,
             self.backend,
             batch_size=batch_size,
             shuffle=True,
             num_workers=0,
             drop_last=False
         )

    def test_dataloader(self, batch_size):
        return DataLoader(
             self.val_dataset,
             self.backend,
             batch_size=batch_size,
             shuffle=True,
             num_workers=0,
             drop_last=False
         )

    def get_sample_X(self, frac: float | None = None):
        train_X, _ = self.get_samples(frac)
        return train_X

    def get_samples(self, frac: float | None = None):
        if frac is None:
            frac = 0.1
        train_X, train_y = self.train_dataset[:]
        train_size = int(len(train_X) * frac)
        return train_X[:train_size], train_y[:train_size]
