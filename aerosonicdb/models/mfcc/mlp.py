import os
import numpy as np
import tensorflow.keras as keras
import tensorflow as tf
from scikeras.wrappers import KerasClassifier
from sklearn.model_selection import cross_validate
from sklearn.metrics import average_precision_score
from aerosonicdb.utils import get_project_root
from aerosonicdb.utils import fetch_k_fold_cv_indicies
from aerosonicdb.utils import load_train_data
from aerosonicdb.utils import load_test_data
from aerosonicdb.utils import train_val_split
from aerosonicdb.utils import load_env_test_data
import absl.logging
absl.logging.set_verbosity(absl.logging.ERROR)
tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.FATAL)


root_path = get_project_root()
feat_path = os.path.join(root_path, 'data/processed')
train_path = os.path.join(feat_path, '13_mfcc_5_train.json')
test_path = os.path.join(feat_path, '13_mfcc_5_test.json')
env_feat_base = '_ENV_13_mfcc_5.json'
output_path = os.path.join(root_path, 'models')


def build_model(x):
    model = keras.Sequential([

        # input layer
        keras.layers.Flatten(input_shape=(x.shape[1], x.shape[2])),

        # 1st dense layer
        keras.layers.Dense(128, activation='relu', kernel_regularizer=keras.regularizers.l2(0.001)),
        keras.layers.Dropout(0.4),

        # 2nd dense layer
        keras.layers.Dense(32, activation='relu', kernel_regularizer=keras.regularizers.l2(0.001)),
        keras.layers.Dropout(0.4),

        # output layer
        keras.layers.Dense(1, activation='sigmoid')
    ])

    # compile model
    optimiser = keras.optimizers.Adam(learning_rate=0.001)
    model.compile(optimizer=optimiser,
                  loss='BinaryCrossentropy',
                  metrics=[tf.keras.metrics.AUC(curve='PR', name='PR-AUC')])

    return model


def run_cv(train_path=train_path, test_path=test_path, epochs=1, batch_size=216, rand_seed=0, verbose=0, k=10):
    keras.utils.set_random_seed(rand_seed)
    X, y, g = load_train_data(data_path=train_path, target_label='class_label')
    build = build_model(X)
    model = KerasClassifier(model=build, epochs=epochs, batch_size=batch_size, random_state=rand_seed, verbose=verbose)
    print(f'Running {k}-fold cross-validation...')
    results = cross_validate(model, X, y,
                             cv=fetch_k_fold_cv_indicies(X, y, g, k=k),
                             scoring='average_precision',
                             return_estimator=True)

    # print(sorted(results.keys()))
    print('CV results:', results['test_score'], sep='\n')

    cv_mean = results['test_score'].mean() * 100
    cv_st_dev = results['test_score'].std() * 100

    print(f'Average Precision Score for 10-fold CV: %.2f%% (%.2f%%)' % (cv_mean, cv_st_dev))

    cv_scores = (cv_mean, cv_st_dev, results['test_score'])

    cv_estimators = results['estimator']
    print(f'\nRunning {k}-model evaluation against Test set...')
    X_test, y_test = load_test_data(data_path=test_path, target_label='class_label')

    eval_results = []
    for est in cv_estimators:
        y_prob = est.predict_proba(X_test, batch_size=batch_size)[:, 1]
        # print(y_test[:5])
        # print(y_prob.shape)
        # print(y_prob[:10])
        ap_score = average_precision_score(y_true=y_test, y_score=y_prob)
        eval_results.append(ap_score)

    print('Test evaluation results:', eval_results, sep='\n')

    test_mean = np.mean(eval_results) * 100
    test_st_dev = np.std(eval_results) * 100
    print(f'Average Precision Score against Test set: %.2f%% (%.2f%%)' % (test_mean, test_st_dev))

    test_scores = (test_mean, test_st_dev, eval_results)

    print(f'\nRunning {k}-model evaluation against the Environment set...')
    # evaluate against the environment set
    X_test, y_test = load_env_test_data(data_path=feat_path, json_base=env_feat_base, target_label='class_label')

    env_results = []
    for est in cv_estimators:
        y_prob = est.predict_proba(X_test, batch_size=batch_size)[:, 1]
        # print(y_test[:5])
        # print(y_prob.shape)
        # print(y_prob[:10])
        ap_score = average_precision_score(y_true=y_test, y_score=y_prob)
        env_results.append(ap_score)

    print('Environment evaluation results:', env_results, sep='\n')

    env_mean = np.mean(env_results) * 100
    env_st_dev = np.std(env_results) * 100
    print(f'Average Precision Score against Environment set: %.2f%% (%.2f%%)' % (env_mean, env_st_dev))
    env_scores = (env_mean, env_st_dev, env_results)

    return cv_scores, test_scores, env_scores


def train_save_model(output_path=output_path,
                     train_path=train_path,
                     filename='mfcc_mlp', 
                     epochs=1, 
                     batch_size=216, 
                     verbose=0,
                     rand_seed=0):
    
    keras.utils.set_random_seed(rand_seed)

    X, y, g = load_train_data(data_path=train_path, target_label='class_label')

    X_train, y_train, X_val, y_val = train_val_split(X, y, g)

    model = build_model(X)
    model.summary()

    # train model
    model.fit(X_train, y_train, validation_data=(X_val, y_val), batch_size=batch_size, epochs=epochs, verbose=verbose)

    # save the model
    model_path = os.path.join(output_path, filename, 'model')
    model.save(model_path)
    
    print(f'Model saved to {model_path}.\n')


if __name__ == '__main__':
    run_cv()
