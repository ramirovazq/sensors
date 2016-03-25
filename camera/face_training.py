import os
import numpy as np
from skimage import io as sio
from skimage import color
from skimage import filters
from skimage import transform
from sklearn import preprocessing

import tensorflow as tf
import cPickle as pickle

FACE_FOLDER_PATH = "/home/alejandro/Pictures/face/"
CHECK_POINT_PATH = "/home/alejandro/data/face_recog/"
FACE_TEST_FOLDER_PATH = "/home/alejandro/Pictures/test/"
DATASET_PATH = "/home/alejandro/data/dataset/"

np.random.seed(133)

class ProcessImages(object):
    def __init__(self, image_size):
        self.image_size = image_size

    def load_images(self, folder):
        folder = FACE_FOLDER_PATH
        images = os.listdir(folder)
        max_num_images = len(images)
        self.dataset = np.ndarray(
            shape=(max_num_images, self.image_size, self.image_size), dtype=np.float32)
        self.labels = np.ndarray(shape=(max_num_images), dtype=np.float32)
        #min_max_scaler = preprocessing.MinMaxScaler()
        for image_index, image in enumerate(images):
            image_file = os.path.join(folder, image)
            image_data = sio.imread(image_file)
            number_id = image.split("-")[1]
            if image_data.shape != (self.image_size, self.image_size):
                raise Exception('Unexpected image shape: %s' % str(image_data.shape))
            image_data = image_data.astype(float)
            self.dataset[image_index, :, :] = preprocessing.scale(image_data)
            self.labels[image_index] = number_id
        num_images = image_index
        print 'Full dataset tensor:', self.dataset.shape
        print 'Mean:', np.mean(self.dataset)
        print 'Standard deviation:', np.std(self.dataset)
        print 'Labels:', self.labels.shape

    def randomize(self, dataset, labels):
        permutation = np.random.permutation(labels.shape[0])
        shuffled_dataset = dataset[permutation,:,:]
        shuffled_labels = labels[permutation]
        return shuffled_dataset, shuffled_labels

    def save_dataset(self, name, valid_size_p=.1, train_size_p=.6):
        total_size = self.dataset.shape[0]
        valid_size = total_size * valid_size_p
        train_size = total_size * train_size_p
        v_t_size = valid_size + train_size
        train_dataset, train_labels = self.randomize(self.dataset[:v_t_size], self.labels[:v_t_size])
        valid_dataset = train_dataset[:valid_size,:,:]
        valid_labels = train_labels[:valid_size]
        train_dataset = train_dataset[valid_size:v_t_size,:,:]
        train_labels = train_labels[valid_size:v_t_size]
        test_dataset, test_labels = self.randomize(
            self.dataset[v_t_size:total_size], self.labels[v_t_size:total_size])
        
        try:
            f = open(DATASET_PATH+name, 'wb')
            save = {
                'train_dataset': train_dataset,
                'train_labels': train_labels,
                'valid_dataset': valid_dataset,
                'valid_labels': valid_labels,
                'test_dataset': test_dataset,
                'test_labels': test_labels,
                }
            pickle.dump(save, f, pickle.HIGHEST_PROTOCOL)
            f.close()
        except Exception as e:
            print('Unable to save data to: ', DATASET_PATH+name, e)
            raise

        print("Test set: {}, Valid set: {}, Training set: {}".format(
            test_labels.shape[0], valid_labels.shape[0], train_labels.shape[0]))

    @classmethod
    def load_dataset(self, name):
        with open(DATASET_PATH+name, 'rb') as f:
            save = pickle.load(f)
            print('Training set', save['train_dataset'].shape, save['train_labels'].shape)
            print('Validation set', save['valid_dataset'].shape, save['valid_labels'].shape)
            print('Test set', save['test_dataset'].shape, save['test_labels'].shape)
            return save

    def process_images(self, images):
        for score, image, d, idx in images:
            print(image.shape, score)
            img = image[d.top():d.bottom(), d.left():d.right(), 0:3]
            img_gray = color.rgb2gray(img)
            if (self.image_size, self.image_size) < img_gray.shape or\
                img_gray.shape < (self.image_size, self.image_size):
                img_gray = transform.resize(img_gray, (self.image_size, self.image_size))
                img_gray = filters.gaussian_filter(img_gray, .5)
            yield img_gray

    def save_images(self, url, number_id, images):
        if len(images) > 0:
            for i, image in enumerate(self.process_images(images)):
                sio.imsave(url+"face-{}-{}.png".format(number_id, i), image)

class BasicFaceClassif(object):
    def __init__(self, model_name, image_size=90):
        self.image_size = image_size
        self.model_name = model_name
        self.model = None
        self.load_dataset()

    def reformat(self, dataset, labels):
        dataset = dataset.reshape((-1, self.image_size * self.image_size)).astype(np.float32)
        return dataset, labels

    def reformat_all(self):
        self.train_dataset, self.train_labels = self.reformat(self.train_dataset, self.train_labels)
        self.valid_dataset, self.valid_labels = self.reformat(self.valid_dataset, self.valid_labels)
        self.test_dataset, self.test_labels = self.reformat(self.test_dataset, self.test_labels)
        print('Training set', self.train_dataset.shape, self.train_labels.shape)
        print('Validation set', self.valid_dataset.shape, self.valid_labels.shape)
        print('Test set', self.test_dataset.shape, self.test_labels.shape)

    def load_dataset(self):
        data = ProcessImages.load_dataset(self.model_name)
        self.train_dataset = data['train_dataset']
        self.train_labels = data['train_labels']
        self.valid_dataset = data['valid_dataset']
        self.valid_labels = data['valid_labels']
        self.test_dataset = data['test_dataset']
        self.test_labels = data['test_labels']
        self.reformat_all()
        del data

class SVCFace(BasicFaceClassif):
    def __init__(self, model_name, image_size=90):
        super(SVCFace, self).__init__(model_name, image_size=image_size)

    def fit(self):
        #from sklearn.linear_model import LogisticRegression
        from sklearn import svm
        #reg = LogisticRegression(penalty='l2')
        reg = svm.LinearSVC(C=1.0, max_iter=1000)
        reg = reg.fit(self.train_dataset, self.train_labels)
        self.model = reg

    def train(self):
        score = self.model.score(self.test_dataset, self.test_labels)
        print('Test accuracy: %.1f%%' % (score*100))
        self.save_model()
        return score

    def predict_set(self, imgs):
        if self.model is None:
            self.load_model()
        return [self.predict(img) for img in imgs]

    def transform_img(self, img):
        return img.reshape((-1, self.image_size*self.image_size)).astype(np.float32)

    def predict(self, img):
        img = self.transform_img(img)
        if self.model is None:
            self.load_model()
        return str(int(self.model.predict(img)[0]))

    def save_model(self):
        from sklearn.externals import joblib
        joblib.dump(self.model, '{}.pkl'.format(CHECK_POINT_PATH+self.model_name)) 

    def load_model(self):
        from sklearn.externals import joblib
        self.model = joblib.load('{}.pkl'.format(CHECK_POINT_PATH+self.model_name))


class BasicTensor(BasicFaceClassif):
    def __init__(self, model_name, batch_size, image_size=90):
        super(BasicTensor, self).__init__(model_name, image_size=image_size)
        self.batch_size = batch_size
        self.check_point = CHECK_POINT_PATH
        
    def accuracy(self, predictions, labels):
        return (100.0 * np.sum(np.argmax(predictions, 1) == np.argmax(labels, 1))
            / predictions.shape[0])

    def reformat(self, dataset, labels):
        dataset = dataset.reshape((-1, self.image_size * self.image_size)).astype(np.float32)
        # Map 0 to [1.0, 0.0, 0.0 ...], 1 to [0.0, 1.0, 0.0 ...]
        labels = (np.arange(self.num_labels) == labels[:,None]).astype(np.float32)
        return dataset, labels

    def fit(self):
        self.graph = tf.Graph()
        with self.graph.as_default():
            # Input data. For the training data, we use a placeholder that will be fed
            # at run time with a training minibatch.
            self.tf_train_dataset = tf.placeholder(tf.float32,
                                            shape=(self.batch_size, self.image_size * self.image_size))
            self.tf_train_labels = tf.placeholder(tf.float32, shape=(self.batch_size, self.num_labels))
            self.tf_valid_dataset = tf.constant(self.valid_dataset)
            self.tf_test_dataset = tf.constant(self.test_dataset)

            # Variables.
            weights = tf.Variable(
            tf.truncated_normal([self.image_size * self.image_size, self.num_labels]))
            biases = tf.Variable(tf.zeros([self.num_labels]))

            # Training computation.
            self.logits = tf.matmul(self.tf_train_dataset, weights) + biases
            self.loss = tf.reduce_mean(
            tf.nn.softmax_cross_entropy_with_logits(self.logits, self.tf_train_labels))

            # Optimizer.
            self.optimizer = tf.train.GradientDescentOptimizer(0.5).minimize(self.loss)

            # Predictions for the training, validation, and test data.
            self.train_prediction = tf.nn.softmax(self.logits)
            self.valid_prediction = tf.nn.softmax(
                tf.matmul(self.tf_valid_dataset, weights) + biases)
            self.test_prediction = tf.nn.softmax(tf.matmul(self.tf_test_dataset, weights) + biases)

    def train(self, num_steps=3001):
        with tf.Session(graph=self.graph) as session:
            saver = tf.train.Saver()
            tf.initialize_all_variables().run()
            print "Initialized"
            for step in xrange(num_steps):
                # Pick an offset within the training data, which has been randomized.
                # Note: we could use better randomization across epochs.
                offset = (step * self.batch_size) % (self.train_labels.shape[0] - self.batch_size)
                # Generate a minibatch.
                batch_data = self.train_dataset[offset:(offset + self.batch_size), :]
                batch_labels = self.train_labels[offset:(offset + self.batch_size), :]
                # Prepare a dictionary telling the session where to feed the minibatch.
                # The key of the dictionary is the placeholder node of the graph to be fed,
                # and the value is the numpy array to feed to it.
                feed_dict = {self.tf_train_dataset : batch_data, self.tf_train_labels : batch_labels}
                _, l, predictions = session.run(
                [self.optimizer, self.loss, self.train_prediction], feed_dict=feed_dict)
                if (step % 500 == 0):
                    print "Minibatch loss at step", step, ":", l
                    print "Minibatch accuracy: %.1f%%" % self.accuracy(predictions, batch_labels)
                    print "Validation accuracy: %.1f%%" % self.accuracy(
                      self.valid_prediction.eval(), self.valid_labels)
            score_v = self.accuracy(self.test_prediction.eval(), self.test_labels)
            print('Test accuracy: %.1f' % score_v)
            saver.save(session, '{}{}.ckpt'.format(self.check_point, self.model_name), global_step=step)
            return score_v

class TestTensor(BasicTensor):
    def __init__(self, *args, **kwargs):
        self.num_labels = 10
        super(TestTensor, self).__init__(*args, **kwargs)

class TensorFace(BasicTensor):
    def __init__(self, model_name, batch_size, image_size=90):
        self.labels_d = dict(enumerate(["106", "110", "155", "222"]))
        self.labels_i = {v: k for k, v in self.labels_d.items()}
        self.num_labels = len(self.labels_d)
        super(TensorFace, self).__init__(model_name, batch_size, image_size=image_size)

    def reformat(self, dataset, labels):
        dataset = dataset.reshape((-1, self.image_size * self.image_size)).astype(np.float32)
        new_labels = np.asarray([self.labels_i[str(int(label))] for label in labels])
        labels_m = (np.arange(len(self.labels_d)) == new_labels[:,None]).astype(np.float32)
        return dataset, labels_m

    def position_index(self, label):
        for i, e in enumerate(label):
            if e == 1:
                return i

    def convert_label(self, label):
        #[0, 0, 1.0] -> 155
        try:
            return self.labels_d[self.position_index(label)]
        except KeyError:
            return None

    def predict_set(self, imgs):
        self.batch_size = 1
        self.fit()
        return [self.predict(img) for img in imgs]
        
    def transform_img(self, img):
        return img.reshape((-1, self.image_size*self.image_size)).astype(np.float32)

    def predict(self, img):
        img = self.transform_img(img)
        with tf.Session(graph=self.graph) as session:
            saver = tf.train.Saver()
            ckpt = tf.train.get_checkpoint_state(self.check_point)
            if ckpt and ckpt.model_checkpoint_path:
                saver.restore(session, ckpt.model_checkpoint_path)
            else:
                print("...no checkpoint found...")

            feed_dict = {self.tf_train_dataset: img}
            classification = session.run(self.train_prediction, feed_dict=feed_dict)
            #print(classification)
            return self.convert_label(classification[0])

class Tensor2LFace(TensorFace):
    def layers(self):
        size = 1
        W1 = tf.Variable(
            tf.truncated_normal([self.image_size * self.image_size, size]), name='weights')
        b1 = tf.Variable(tf.zeros([size]), name='biases')
        hidden = tf.nn.relu(tf.matmul(self.tf_train_dataset, W1) + b1)

        W2 = tf.Variable(
            tf.truncated_normal([size, self.num_labels]))
        b2 = tf.Variable(tf.zeros([self.num_labels]))

        hidden = tf.nn.dropout(hidden, 0.5, seed=66478)
        self.logits = tf.matmul(hidden, W2) + b2
        return W1, b1, W2, b2

    def fit(self):
        self.graph = tf.Graph()
        with self.graph.as_default():
            self.tf_train_dataset = tf.placeholder(tf.float32,
                                            shape=(self.batch_size, self.image_size * self.image_size))
            self.tf_train_labels = tf.placeholder(tf.float32, shape=(self.batch_size, self.num_labels))
            self.tf_valid_dataset = tf.constant(self.valid_dataset)
            self.tf_test_dataset = tf.constant(self.test_dataset)

            W1, b1, W2, b2 = self.layers()

            self.loss = tf.reduce_mean(
                tf.nn.softmax_cross_entropy_with_logits(self.logits, self.tf_train_labels))

            regularizers = tf.nn.l2_loss(W1) + tf.nn.l2_loss(b1) + tf.nn.l2_loss(W2) + tf.nn.l2_loss(b2)
            self.loss += 5e-4 * regularizers

            self.optimizer = tf.train.GradientDescentOptimizer(0.5).minimize(self.loss)

            self.train_prediction = tf.nn.softmax(self.logits)
            hidden_valid =  tf.nn.relu(tf.matmul(self.tf_valid_dataset, W1) + b1)
            valid_logits = tf.matmul(hidden_valid, W2) + b2
            self.valid_prediction = tf.nn.softmax(valid_logits)
            hidden_test = tf.nn.relu(tf.matmul(self.tf_test_dataset, W1) + b1)
            test_logits = tf.matmul(hidden_test, W2) + b2
            self.test_prediction = tf.nn.softmax(test_logits)


class ConvTensorFace(TensorFace):
    def __init__(self, model_name, batch_size, image_size=90):
        self.num_channels = 1
        self.patch_size = 5
        self.depth = 90
        self.num_hidden = 64
        super(ConvTensorFace, self).__init__(model_name, batch_size, image_size=image_size)        

    def reformat(self, dataset, labels):
        dataset = dataset.reshape((-1, self.image_size, self.image_size, self.num_channels)).astype(np.float32)
        new_labels = np.asarray([self.labels_i[str(int(label))] for label in labels])
        labels_m = (np.arange(len(self.labels_d)) == new_labels[:,None]).astype(np.float32)
        return dataset, labels_m

    def layers(self, data, layer1_weights, layer1_biases, layer2_weights, layer2_biases, 
            layer3_weights, layer3_biases, dropout=False):
        conv = tf.nn.conv2d(data, layer1_weights, [1, 2, 2, 1], padding='SAME')
        hidden = tf.nn.relu(conv + layer1_biases)
        pool = tf.nn.max_pool(hidden,
                              ksize=[1, 2, 2, 1],
                              strides=[1, 2, 2, 1],
                              padding='SAME')
        shape = pool.get_shape().as_list()
        reshape = tf.reshape(pool, [shape[0], shape[1] * shape[2] * shape[3]])
        hidden = tf.nn.relu(tf.matmul(reshape, layer2_weights) + layer2_biases)
        if dropout:
            hidden = tf.nn.dropout(hidden, 0.5, seed=66478)
        return tf.matmul(hidden, layer3_weights) + layer3_biases

    def fit(self):
        import math
        self.graph = tf.Graph()
        with self.graph.as_default():
            self.tf_train_dataset = tf.placeholder(
                tf.float32, shape=(self.batch_size, self.image_size, self.image_size, self.num_channels))
            self.tf_train_labels = tf.placeholder(tf.float32, shape=(self.batch_size, self.num_labels))
            self.tf_valid_dataset = tf.constant(self.valid_dataset)
            self.tf_test_dataset = tf.constant(self.test_dataset)

            # Variables.
            layer3_size = int(math.ceil(self.image_size / 4.))
            layer1_weights = tf.Variable(tf.truncated_normal(
                [self.patch_size, self.patch_size, self.num_channels, self.depth], stddev=0.1))
            layer1_biases = tf.Variable(tf.zeros([self.depth]))
            layer2_weights = tf.Variable(tf.truncated_normal(
                [layer3_size * layer3_size * self.depth, self.num_hidden], stddev=0.1)) # 4 num of ksize
            layer2_biases = tf.Variable(tf.constant(1.0, shape=[self.num_hidden]))
            layer3_weights = tf.Variable(tf.truncated_normal(
                [self.num_hidden, self.num_labels], stddev=0.1))
            layer3_biases = tf.Variable(tf.constant(1.0, shape=[self.num_labels]))

            self.logits = self.layers(self.tf_train_dataset, layer1_weights, 
                layer1_biases, layer2_weights, layer2_biases, layer3_weights, 
                layer3_biases, dropout=True)

            self.loss = tf.reduce_mean(
                tf.nn.softmax_cross_entropy_with_logits(self.logits, self.tf_train_labels))
            regularizers = tf.nn.l2_loss(layer1_weights) + tf.nn.l2_loss(layer1_biases) +\
            tf.nn.l2_loss(layer2_weights) + tf.nn.l2_loss(layer2_biases) +\
            tf.nn.l2_loss(layer3_weights) + tf.nn.l2_loss(layer3_biases)
            self.loss += 5e-4 * regularizers

            # Optimizer: set up a variable that's incremented once per batch and
            # controls the learning rate decay.
            batch = tf.Variable(0)
            # Decay once per epoch, using an exponential schedule starting at 0.01.
            learning_rate = tf.train.exponential_decay(
              0.01,                # Base learning rate.
              batch * self.batch_size,  # Current index into the dataset.
              23,          # train_labels.shape[0] Decay step.
              0.95,                # Decay rate.
              staircase=True)
            self.optimizer = tf.train.MomentumOptimizer(learning_rate, 0.9).minimize(self.loss,
                global_step=batch)

            # Predictions for the training, validation, and test data.
            self.train_prediction = tf.nn.softmax(self.logits)
            self.valid_prediction = tf.nn.softmax(self.layers(self.tf_valid_dataset, layer1_weights, 
                layer1_biases, layer2_weights, layer2_biases, layer3_weights, 
                layer3_biases))
            self.test_prediction = tf.nn.softmax(self.layers(self.tf_test_dataset, layer1_weights, 
                layer1_biases, layer2_weights, layer2_biases, layer3_weights, 
                layer3_biases))

    def train(self, num_steps=0):
        with tf.Session(graph=self.graph) as session:
            saver = tf.train.Saver()
            tf.initialize_all_variables().run()
            print("Initialized")
            for step in xrange(int(150 * self.train_labels.shape[0]) // self.batch_size):
                offset = (step * self.batch_size) % (self.train_labels.shape[0] - self.batch_size)
                batch_data = self.train_dataset[offset:(offset + self.batch_size), :, :, :]
                batch_labels = self.train_labels[offset:(offset + self.batch_size), :]
                feed_dict = {self.tf_train_dataset : batch_data, self.tf_train_labels : batch_labels}
                _, l, predictions = session.run(
                [self.optimizer, self.loss, self.train_prediction], feed_dict=feed_dict)
                if (step % 5000 == 0):
                    print "Minibatch loss at step", step, ":", l
                    print "Minibatch accuracy: %.1f%%" % self.accuracy(predictions, batch_labels)
                    print "Validation accuracy: %.1f%%" % self.accuracy(
                    self.valid_prediction.eval(), self.valid_labels)
            score = self.accuracy(self.test_prediction.eval(), self.test_labels)
            print('Test accuracy: %.1f' % score)
            saver.save(session, '{}{}.ckpt'.format(self.check_point, self.model_name), global_step=step)
            return score

    def transform_img(self, img):
        return img.reshape((-1, self.image_size, self.image_size, self.num_channels)).astype(np.float32)


if __name__  == '__main__':
    #face_classif = SVCFace("basic_4", image_size=90)
    #face_classif = TensorFace("basic_4", 10, image_size=90)
    #face_classif = Tensor2LFace("basic_4", 10, image_size=90)
    face_classif = ConvTensorFace("basic_4", 10, image_size=90)
    face_classif.fit()
    face_classif.train(num_steps=3001)