# WGAN-GP实战
import os
import tensorflow as tf
from tensorflow import keras
import numpy as np
from PIL import Image
import glob
from gan import Generator, Discriminator
from dataset import make_anime_dataset

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


def save_result(val_out, val_block_size, image_path, color_mode):
    def preprocess(img):
        img = ((img + 1.0) * 127.5).astype(np.uint8)
        # img = img.astype(np.uint8)
        return img

    preprocessed = preprocess(val_out)
    final_image = np.array([])
    single_row = np.array([])
    for b in range(val_out.shape[0]):
        # concat image into a row
        if single_row.size == 0:
            single_row = preprocessed[b, :, :, :]
        else:
            single_row = np.concatenate((single_row, preprocessed[b, :, :, :]), axis=1)

        # concat image row to final_image
        if (b + 1) % val_block_size == 0:
            if final_image.size == 0:
                final_image = single_row
            else:
                final_image = np.concatenate((final_image, single_row), axis=0)

            # reset single row
            single_row = np.array([])

    if final_image.shape[2] == 1:
        final_image = np.squeeze(final_image, axis=2)
    Image.fromarray(final_image).convert('RGB').save(image_path)


def gradient_penalty(discriminator, batch_x, fake_image):
    # 梯度惩罚项计算函数
    batchsz = batch_x.shape[0]

    # 每个样本均随机采样t，用于插值
    t = tf.random.uniform([batchsz, 1, 1, 1])
    # 自动扩展为x的形状，[b, 1, 1, 1] => [b, h, w, c]
    t = tf.broadcast_to(t, batch_x.shape)
    # 在真假图片之间做线性插值
    interpolate = t * batch_x + (1 - t) * fake_image
    # 在梯度环境中计算D对插值样本对梯度
    with tf.GradientTape() as tape:
        tape.watch([interpolate])  # 加入梯度观察列表
        d_interpolate_logits = discriminator(interpolate)
    grads = tape.gradient(d_interpolate_logits, interpolate)

    # 计算每个样本对梯度对范数：[b, h, w, c] => [b, -1]
    grads = tf.reshape(grads, [grads.shape[0], -1])
    gp = tf.norm(grads, axis=1)  # [b]
    # 计算梯度惩罚项
    gp = tf.reduce_mean((gp - 1.) ** 2)

    return gp


def d_loss_fn(generator, discriminator, batch_z, batch_x, is_training):
    # 计算D的损失函数
    fake_image = generator(batch_z, is_training)  # 假样本
    # 判定生成图片
    d_fake_logits = discriminator(fake_image, is_training)  # 假样本的输出
    # 判定真实图片
    d_real_logits = discriminator(batch_x, is_training)  # 真样本的输出
    # 计算梯度惩罚项
    gp = gradient_penalty(discriminator, batch_x, fake_image)
    # WGAN-GP D损失函数的定义，这里并不是计算交叉熵，而是直接最大化正样本的输出
    # 最小化假样本的输出和梯度惩罚项
    # 真实图片与1之间的误差
    loss = tf.reduce_mean(d_fake_logits) - tf.reduce_mean(d_real_logits) + 10. * gp

    return loss, gp


def g_loss_fn(generator, discriminator, batch_z, is_training):
    # 生成器的损失函数
    fake_image = generator(batch_z, is_training)
    # 在训练生成网络时，需要迫使生成图片判定为真
    d_fake_logits = discriminator(fake_image, is_training)
    # WGAN-GP G损失函数，最大化假样本的输出值
    loss = - tf.reduce_mean(d_fake_logits)

    return loss


def main():
    tf.random.set_seed(3333)
    np.random.seed(3333)
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
    assert tf.__version__.startswith('2.')

    z_dim = 100  # 隐藏向量z的长度
    epochs = 3000000  # 训练步数
    batch_size = 64
    learning_rate = 0.0002
    is_training = True

    # 获取数据集路径
    img_path = glob.glob(r'C:\Users\jay_n\.keras\datasets\faces\*.jpg') + \
        glob.glob(r'C:\Users\jay_n\.keras\datasets\faces\*.png')
    print('images num:', len(img_path))
    # 构建数据集对象
    dataset, img_shape, _ = make_anime_dataset(img_path, batch_size, resize=64)
    print(dataset, img_shape)
    sample = next(iter(dataset))  # 采样
    print(sample.shape, tf.reduce_max(sample).numpy(), tf.reduce_min(sample).numpy())
    dataset = dataset.repeat(100)
    db_iter = iter(dataset)

    generator = Generator()
    generator.build(input_shape=(4, z_dim))
    discriminator = Discriminator()
    discriminator.build(input_shape=(4, 64, 64, 3))
    # 分别为生成器和判别器创建优化器
    g_optimizer = keras.optimizers.Adam(learning_rate=learning_rate, beta_1=0.5)
    d_optimizer = keras.optimizers.Adam(learning_rate=learning_rate, beta_1=0.5)

    # generator.load_weights('generator.ckpt')
    # discriminator.load_weights('discriminator.ckpt')
    # print('Loaded ckpt!!')

    d_losses, g_losses = [], []
    for epoch in range(epochs):
        # 1. 训练判别器
        for _ in range(1):
            # 采样隐藏向量
            batch_z = tf.random.normal([batch_size, z_dim])
            batch_x = next(db_iter)  # 采样真实图片
            # 判别器前向计算
            with tf.GradientTape() as tape:
                d_loss, _ = d_loss_fn(generator, discriminator, batch_z, batch_x, is_training)
            grads = tape.gradient(d_loss, discriminator.trainable_variables)
            d_optimizer.apply_gradients(zip(grads, discriminator.trainable_variables))
        # 2. 训练生成器
        # 采样隐藏向量
        batch_z = tf.random.normal([batch_size, z_dim])
        # 生成器前向计算
        with tf.GradientTape() as tape:
            g_loss = g_loss_fn(generator, discriminator, batch_z, is_training)
        grads = tape.gradient(g_loss, generator.trainable_variables)
        g_optimizer.apply_gradients(zip(grads, generator.trainable_variables))

        if epoch % 100 == 0:
            print(epoch, 'd-loss:', float(d_loss), 'g-loss:', float(g_loss))
            # 可视化
            z = tf.random.normal([100, z_dim])
            fake_image = generator(z, training=False)
            img_path = os.path.join('gan_images', 'gan-%d.png' % epoch)
            save_result(fake_image.numpy(), 10, img_path, color_mode='P')

        d_losses.append(float(d_loss))
        g_losses.append(float(g_loss))

        if epoch % 10000 == 1:
            generator.save_weights('generator.ckpt')
            discriminator.save_weights('discriminator.ckpt')


if __name__ == '__main__':
    main()
