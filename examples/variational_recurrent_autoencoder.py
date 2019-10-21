'''
Example of VRAE on text data
VRAE, like VAE, has a modular design. encoder, decoder, and VRAE are 3 models that share weights. After training the VRAE model,
the encoder can be used to generate latent vectors of text data(sentences/documents).
The decoder can be used to generate embedding vector of text by sampling the latent vector from a Gaussian distribution with mean = 0 and std = 1.
# Reference
[1] Samuel R. Bowman, Luke Vilnis, Oriol Vinyals, Andrew M. Dai, Rafal Jozefowicz, and Samy Bengio.
"Generating Sentences from a Continuous Space."
https://arxiv.org/abs/1511.06349
'''

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from keras.preprocessing import sequence
from keras.layers import Lambda, Input, Embedding, Dense, LSTM, RepeatVector, wrappers
from keras.models import Model
from keras.datasets import imdb
from keras.losses import mse, binary_crossentropy
from keras.utils import plot_model
from keras import backend as K

import numpy as np
import matplotlib.pyplot as plt
import argparse
import os

# reparameterization trick
# instead of sampling from Q(z|X), sample epsilon = N(0,I)
# z = z_mean + sqrt(var) * epsilon
def sampling(args):
    """Reparameterization trick by sampling from an isotropic unit Gaussian.
    # Arguments
        args (tensor): mean and log of variance of Q(z|X)
    # Returns
        z (tensor): sampled latent vector
    """

    z_mean, z_log_var = args
    batch = K.shape(z_mean)[0]
    dim = K.int_shape(z_mean)[1]
    # by default, random_normal has mean = 0 and std = 1.0
    epsilon = K.random_normal(shape=(batch, dim))
    return z_mean + K.exp(0.5 * z_log_var) * epsilon

# IMDB dataset
max_features = 20000
# cut texts after this number of words
# (among top max_features most common words)
maxlen = 100

print('Loading data...')
(x_train, y_train), (x_test, y_test) = imdb.load_data(num_words=max_features)
print(len(x_train), 'train sequences')
print(len(x_test), 'test sequences')

print('Pad sequences (samples x time)')
x_train = sequence.pad_sequences(x_train, maxlen=maxlen)
x_test = sequence.pad_sequences(x_test, maxlen=maxlen)
y_train = np.array(y_train)
y_test = np.array(y_test)

# network parameters
input_shape = (maxlen, )
embed_dim = 32
intermediate_dim = 512
latent_dim = 256
batch_size = 512
epochs = 50

# VRAE model = encoder + decoder
# build encoder model
inputs = Input(shape=input_shape, name='encoder_inputs')
embedding_layer = Embedding(max_features, embed_dim, input_length=maxlen, trainable=True)
encoder_inputs = embedding_layer(inputs)
x, h, c = LSTM(intermediate_dim, return_state=True)(encoder_inputs)
z_mean = Dense(latent_dim, name='z_mean')(x)
z_log_var = Dense(latent_dim, name='z_log_var')(x)

# use reparameterization trick to push the sampling out as input
# note that "output_shape" isn't necessary with the TensorFlow backend
z = Lambda(sampling, output_shape=(latent_dim,), name='z')([z_mean, z_log_var])

# instantiate encoder model
encoder = Model(inputs, [z_mean, z_log_var, z, h, c], name='encoder')
encoder.summary()

# build decoder model
latent_inputs = Input(shape=(latent_dim,), name='z')
latent_repeat = RepeatVector(maxlen)(latent_inputs)
h = Input(shape=(intermediate_dim, ), name='encoder_state_h')
c = Input(shape=(intermediate_dim, ), name='encoder_state_c')
x, _, _ = LSTM(intermediate_dim, return_sequences=True, return_state=True)(latent_repeat, initial_state=[h, c])
x, _, _ = LSTM(embed_dim, return_sequences=True, return_state=True)(x)
outputs = wrappers.TimeDistributed(Dense(embed_dim))(x)

# instantiate decoder model
decoder = Model([latent_inputs, h, c], outputs, name='decoder')
decoder.summary()

# instantiate VAE model
outputs = decoder(encoder(inputs)[2:])
vrae = Model(inputs, outputs, name='vrae')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    help_ = "Load h5 model trained weights"
    parser.add_argument("-w", "--weights", help=help_)

    args = parser.parse_args()
    models = (encoder, decoder)
    data = (x_test, y_test)

    # VRAE loss = kl_loss + mse_loss
    reconstruction_loss = mse(encoder_inputs, outputs)
    reconstruction_loss = K.sum(reconstruction_loss, axis=-1)
    kl_loss = 1 + z_log_var - K.square(z_mean) - K.exp(z_log_var)
    kl_loss = K.sum(kl_loss, axis=-1)
    kl_loss *= -0.5
    vrae_loss = K.mean(reconstruction_loss + kl_loss)
    vrae.add_loss(vrae_loss)
    vrae.compile(optimizer='adam')
    vrae.summary()

    if args.weights:
        vrae.load_weights(args.weights)
    else:
        # train the autoencoder
        vrae.fit(x_train,
                epochs=epochs,
                batch_size=batch_size,
                validation_data=(x_test, None))
        vrae.save_weights('vrae_mlp_mnist.h5')
