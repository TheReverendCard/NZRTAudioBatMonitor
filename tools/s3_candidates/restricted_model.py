"""Restricted loader for known local trainer output only; never use untrusted checkpoints."""
def restricted_load(path):
    import numpy as np
    import joblib
    import joblib.numpy_pickle as npp
    allowed = {
        ('sklearn.pipeline','Pipeline'), ('sklearn.linear_model._logistic','LogisticRegression'),
        ('sklearn.preprocessing._data','StandardScaler'),
        ('sklearn.preprocessing._label','LabelBinarizer'),
        ('sklearn.neural_network._multilayer_perceptron','MLPClassifier'),
        ('sklearn.neural_network._stochastic_optimizers','AdamOptimizer'),
        ('numpy._core.multiarray','scalar'), ('numpy','dtype'), ('numpy','ndarray'),
        ('joblib.numpy_pickle','NumpyArrayWrapper'),
        ('numpy._core.multiarray','_reconstruct'),('numpy._core.numeric','_frombuffer'),
        ('numpy.random._pickle','__randomstate_ctor'),
        ('numpy.random._pickle','__bit_generator_ctor'),
        ('numpy.random._pickle','__generator_ctor'),
        ('numpy.random._mt19937','MT19937'),
    }
    class OwnerModelOnlyUnpickler(npp.NumpyUnpickler):
        def find_class(self, module, name):
            if (module,name) not in allowed:
                raise ValueError('Disallowed pickle global %s.%s' % (module,name))
            return super().find_class(module,name)
    old=npp.NumpyUnpickler
    try:
        npp.NumpyUnpickler=OwnerModelOnlyUnpickler
        return joblib.load(path)
    finally:
        npp.NumpyUnpickler=old
