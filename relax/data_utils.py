# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/01_data.utils.ipynb.

# %% ../nbs/01_data.utils.ipynb 1
from __future__ import annotations
from fastcore.test import *
import pandas as pd
import numpy as np
import jax
import jax.numpy as jnp
import einops
from .utils import auto_reshaping


# %% auto 0
__all__ = ['PREPROCESSING_TRANSFORMATIONS', 'DataPreprocessor', 'MinMaxScaler', 'EncoderPreprocessor', 'OrdinalPreprocessor',
           'OneHotEncoder', 'Transformation', 'MinMaxTransformation', 'OneHotTransformation', 'Feature', 'Dataset']

# %% ../nbs/01_data.utils.ipynb 3
def _check_fit_xs(xs: np.ndarray):
    if xs.ndim > 2 or (xs.ndim == 2 and xs.shape[1] != 1):
        raise ValueError(f"MinMaxScaler only supports array with a single feature, but got shape={xs.shape}.")
        
    
class DataPreprocessor:
    
    def fit(self, xs, y=None):
        raise NotImplementedError
    
    def transform(self, xs):
        raise NotImplementedError
    
    def fit_transform(self, xs, y=None):
        self.fit(xs, y)
        return self.transform(xs)
    
    def inverse_transform(self, xs):
        raise NotImplementedError

# %% ../nbs/01_data.utils.ipynb 4
class MinMaxScaler(DataPreprocessor): 
    def fit(self, xs, y=None):
        _check_fit_xs(xs)
        self.min_ = xs.min(axis=0)
        self.max_ = xs.max(axis=0)
        return self
    
    def transform(self, xs):
        return (xs - self.min_) / (self.max_ - self.min_)
    
    def inverse_transform(self, xs):
        return xs * (self.max_ - self.min_) + self.min_

# %% ../nbs/01_data.utils.ipynb 6
class EncoderPreprocessor(DataPreprocessor):
    def _fit(self, xs, y=None):
        _check_fit_xs(xs)
        self.categories_ = np.unique(xs)

    def _transform(self, xs):
        """Transform data to ordinal encoding."""
        ordinal = np.searchsorted(self.categories_, xs)
        return einops.rearrange(ordinal, 'k n -> n k')
    
    def _inverse_transform(self, xs):
        """Transform ordinal encoded data back to original data."""
        return self.categories_[xs].T

# %% ../nbs/01_data.utils.ipynb 7
class OrdinalPreprocessor(EncoderPreprocessor):
    def fit(self, xs, y=None):
        self._fit(xs, y)
        return self
    
    def transform(self, xs):
        if xs.ndim == 1:
            raise ValueError(f"OrdinalPreprocessor only supports 2D array with a single feature, "
                             f"but got shape={xs.shape}.")
        return self._transform(xs)
    
    def inverse_transform(self, xs):
        return self._inverse_transform(xs)

# %% ../nbs/01_data.utils.ipynb 9
class OneHotEncoder(EncoderPreprocessor):
    # Fit the encoder without sci-kit OneHotEncoder.
    def fit(self, xs, y=None):
        self._fit(xs, y)
        return self

    def transform(self, xs):
        if xs.ndim == 1:
            raise ValueError(f"OneHotEncoder only supports 2D array with a single feature, "
                             f"but got shape={xs.shape}.")
        xs_int = self._transform(xs)
        one_hot_feats = jax.nn.one_hot(xs_int, len(self.categories_))
        return einops.rearrange(one_hot_feats, 'k n d -> n (k d)')

    def inverse_transform(self, xs):
        xs_int = np.argmax(xs, axis=-1)
        return self._inverse_transform(xs_int).reshape(-1, 1)

# %% ../nbs/01_data.utils.ipynb 12
class Transformation:
    def __init__(self, name, transformer):
        self.name = name
        self.transformer = transformer

    def fit(self, xs, y=None):
        self.transformer.fit(xs)
        return self
    
    def transform(self, xs):
        return self.transformer.transform(xs)

    def fit_transform(self, xs, y=None):
        return self.transformer.fit_transform(xs)
    
    def inverse_transform(self, xs):
        return self.transformer.inverse_transform(xs)

    def apply_constraint(self, xs):
        return xs

# %% ../nbs/01_data.utils.ipynb 13
class MinMaxTransformation(Transformation):
    def __init__(self):
        super().__init__("minmax", MinMaxScaler())

    def apply_constraint(self, xs, cfs, hard: bool = False):
        return jnp.clip(cfs, 0., 1.)

# %% ../nbs/01_data.utils.ipynb 15
class OneHotTransformation(Transformation):
    def __init__(self):
        super().__init__("ohe", OneHotEncoder())

    @property
    def categories(self) -> int:
        return len(self.transformer.categories_)

    def apply_constraint(self, xs, cfs, hard: bool = False):
        return jax.lax.cond(
            hard,
            true_fun=lambda x: jax.nn.one_hot(jnp.argmax(x, axis=-1), self.categories),
            false_fun=lambda x: jax.nn.softmax(x, axis=-1),
            operand=cfs,
        )

# %% ../nbs/01_data.utils.ipynb 17
PREPROCESSING_TRANSFORMATIONS = {
    'ohe': OneHotTransformation(),
    'minmax': MinMaxTransformation(),
}

# %% ../nbs/01_data.utils.ipynb 19
class Feature:
    
    def __init__(
        self,
        name: str,
        data: np.ndarray,
        transformation: str | Transformation,
        transformed_data = None,
        is_immutable: bool = False,
    ):
        self.name = name
        self.data = data
        if isinstance(transformation, str):
            self.transformation = PREPROCESSING_TRANSFORMATIONS[transformation]
        elif isinstance(transformation, Transformation):
            self.transformation = transformation
        else:
            raise ValueError(f"Unknown transformer {transformation}")
        self._transformed_data = transformed_data
        self.is_immutable = is_immutable

    @property
    def transformed_data(self):
        if self._transformed_data is None:
            return self.fit_transform(self.data)
        else:
            return self._transformed_data

    @classmethod
    def from_dict(cls, d):
        return cls(**d)
    
    def to_dict(self):
        return {
            'name': self.name,
            'data': self.data,
            'transformed_data': self.transformed_data,
            'transformation': self.transformation,
            'is_immutable': self.is_immutable,
        }
    
    def __repr__(self):
        return f"Feature(" \
               f"name={self.name}, \ndata={self.data}, \n" \
               f"transformed_data={self.transformed_data}, \n" \
               f"transformer={self.transformation}, \n" \
               f"is_immutable={self.is_immutable})"
    
    __str__ = __repr__

    def __get_item__(self, idx):
        return {
            'data': self.data[idx],
            'transformed_data': self.transformed_data[idx],
        }

    def fit(self):
        self.transformation.fit(self.data)
        return self
    
    def transform(self, xs):
        return self.transformation.transform(xs)

    def fit_transform(self, xs):
        return self.transformation.fit_transform(xs)
    
    def inverse_transform(self, xs):
        return self.transformation.inverse_transform(xs)
    
    def apply_constraint(self, xs, cfs, hard: bool = False):
        return jax.lax.cond(
            self.is_immutable,
            true_fun=lambda xs: xs,
            false_fun=lambda _: self.transformation.apply_constraint(xs, cfs, hard),
            operand=xs,
        )

# %% ../nbs/01_data.utils.ipynb 21
class Dataset:
    def __init__(
        self,
        features: list[Feature],
        *args, **kwargs
    ):
        self._features = features
        self._feature_indices = []
        self._transformed_data = None

    @property
    def features(self):
        return self._features

    @property
    def feature_indices(self):
        if self._feature_indices is None:
            self._transform_data()
        return self._feature_indices
    
    @property
    def transformed_data(self):
        if self._transformed_data is None:
            self._transform_data()
        return self._transformed_data

    def _transform_data(self):
        self._feature_indices = []
        self._transformed_data = []
        start, end = 0, 0
        for feat in self.features:
            transformed_data = feat.transformed_data
            end += transformed_data.shape[-1]
            self._feature_indices.append((start, end))
            self._transformed_data.append(transformed_data)
            start = end

        self._transformed_data = jnp.concatenate(self._transformed_data, axis=-1)

    def transform(self, data):
        raise NotImplementedError

    def inverse_transform(self, xs):
        raise NotImplementedError

    def apply_constraint(self, xs, cfs, hard: bool = False):
        constrainted_cfs = []
        for (start, end), feat in zip(self.feature_indices, self.features):
            _cfs = feat.apply_constraint(xs[:, start:end], cfs[:, start:end], hard)
            constrainted_cfs.append(_cfs)
        return jnp.concatenate(constrainted_cfs, axis=-1)
