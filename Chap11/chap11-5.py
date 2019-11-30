# 11.5 RNN情感分类问题实战
import tensorflow as tf
import os
from tensorflow.keras import datasets, layers, Sequential, preprocessing, optimizers, losses

tf.random.set_seed(22)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
assert tf.__version__.startswith('2.')

# 获取所有GPU设备列表
gpus = tf.config.experimental.list_physical_devices('GPU')
if gpus:
    try:
        # 设置GPU显存占用为按需分配
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)
        logical_gpus = tf.config.experimental.list_logical_devices('GPU')
        print(len(gpus), "Physical GPUS,", len(logical_gpus), "Logical GPUs")
    except RuntimeError as e:
        # 异常处理
        print(e)

# for SimpleRNNCell computation
tf.compat.v1.disable_eager_execution()

# 11.5.1 数据集
batchsz = 128  # 批量大小
total_words = 10000  # 词汇表大小N_vocab
max_review_len = 80  # 句子最大长度s，大于的句子部分将截断，小于的将填充
embedding_len = 100  # 词向量特征长度f
# 加载IMDB数据集，此处的数据采用数字编码，一个数字代表一个单词
(x_train, y_train), (x_test, y_test) = datasets.imdb.load_data(num_words=total_words)
print(x_train.shape, len(x_train[0]), y_train.shape)
print(x_test.shape, len(x_test[0]), y_test.shape)
# 数字编码表
word_index = datasets.imdb.get_word_index()
# for k, v in word_index.items():
#     print(k, v)
# 前面4个ID是特殊位
word_index = {k: (v + 3) for k, v in word_index.items()}
word_index["<PAD>"] = 0
word_index["<START"] = 1
word_index["<UNK>"] = 2  # unknown
word_index["<UNUSED>"] = 3
# 翻转编码表
reverse_word_index = dict([(value, key) for (key, value) in word_index.items()])


def decode_review(text):
    return ' '.join([reverse_word_index.get(i, '?') for i in text])


print(decode_review(x_train[0]))

# 截断和填充句子，使得等长，此处长句子保留句子后面的部分，短句子在前面填充
x_train = preprocessing.sequence.pad_sequences(x_train, maxlen=max_review_len)
x_test = preprocessing.sequence.pad_sequences(x_test, maxlen=max_review_len)
# 构建数据集，打散，批量，并丢掉最后一个不够batchsz的batch
db_train = tf.data.Dataset.from_tensor_slices((x_train, y_train))
db_train = db_train.shuffle(1000).batch(batchsz, drop_remainder=True)
db_test = tf.data.Dataset.from_tensor_slices((x_test, y_test))
db_test = db_test.batch(batchsz, drop_remainder=True)
print('x_train shape:', x_train.shape, tf.reduce_max(y_train), tf.reduce_min(y_train))
print('x_test shape:', x_test.shape)


# 11.5.2 网络模型
class MyRNN(tf.keras.Model):
    # Cell方式构建多层网络
    def __init__(self, units):
        super(MyRNN, self).__init__()
        # 词向量编码[b, 80] => [b, 80, 100]
        self.embedding = layers.Embedding(total_words, embedding_len, input_length=max_review_len)

        # [b, 64]，构建Cell初始化状态向量，重复使用
        self.state0 = [tf.zeros([batchsz, units])]
        self.state1 = [tf.zeros([batchsz, units])]
        # 构建2个Cell
        self.rnn_cell0 = layers.SimpleRNNCell(units, dropout=0.5)
        self.rnn_cell1 = layers.SimpleRNNCell(units, dropout=0.5)
        '''
        # 构建RNN
        self.rnn = Sequential([
            layers.SimpleRNN(units, dropout=0.5, return_sequences=True),
            layers.SimpleRNN(units, dropout=0.5)
        ])
        '''
        # 构建分类网络，用于将CELL的输出特征进行分类，2分类
        # [b, 80, 100] => [b, 64] => [b, 1]
        self.outlayer = Sequential([
            layers.Dense(units),
            layers.Dropout(rate=0.5),
            layers.ReLU(),
            layers.Dense(1)])

    def call(self, inputs, training=None):
        x = inputs  # [b, 80]
        # embedding: [b, 80] => [b, 80, 100]
        x = self.embedding(x)
        # rnn cell compute, [b, 80, 100] => [b, 64]

        state0 = self.state0
        state1 = self.state1
        for word in tf.unstack(x, axis=1):  # word: [b, 100]
            out0, state0 = self.rnn_cell0(word, state0, training)
            out1, state1 = self.rnn_cell1(out0, state1, training)

        # x = self.rnn(x)
        # 末层最后一个输出作为分类网络的输入：[b, 64] => [b, 1]
        x = self.outlayer(out1, training)
        # x = self.outlayer(x, training)
        # p(y is pos|x)
        prob = tf.sigmoid(x)

        return prob


def main():
    units = 64  # RNN状态向量长度f
    epochs = 20  # 训练epochs

    model = MyRNN(units)
    # 装配
    model.compile(optimizer=optimizers.Adam(0.001),
                  loss=losses.BinaryCrossentropy(),
                  metrics=['accuracy'])
    # 训练和验证
    model.fit(db_train, epochs=epochs, validation_data=db_test)
    # 测试
    model.evaluate(db_test)


if __name__ == '__main__':
    main()