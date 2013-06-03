import unittest
import numpy as np
import pycuda.autoinit
from neural_nets.pycuda_ops.convolution import conv1d_matrix_mult_filter, \
     conv1d_grad_weights, max_pool, max_pool_grad
from pycuda import gpuarray
from pycuda.curandom import rand as curand
from hannes_tools.test_tools import debug_on

class TestConvolution(unittest.TestCase):
    FLOAT_ERR_TOL = 1e-4
    DOUBLE_ERR_TOL = 1e-13
    
    @staticmethod
    def cpu_conv1d(x, w, stride=1, sequence_conv=False):
        n, m = x.shape        
        n_filters, filter_width = w.shape

        if not sequence_conv:
            pad_width = filter_width // 2
            x_padded = np.concatenate((np.zeros((n, pad_width), dtype=x.dtype),
                                       x,
                                       np.zeros((n, pad_width), dtype=x.dtype)), 1)
        else:
            x_padded = np.concatenate((x,
                                       np.zeros((n, filter_width - 1), dtype=x.dtype)), 1)
        m_output = x.shape[1] // stride
        y = np.empty((n_filters, x.shape[0], m_output), dtype=x.dtype)
        for f in range(n_filters):
            for i in range(0, m_output):
                ii = i*stride
                y[f,:,i] = (x_padded[:,ii:(ii+filter_width)]*w[f,:]).sum(1)
        return y

    @staticmethod    
    def gpu_conv1d(x, w, dtype, stride=1, sequence_conv=False):
        y = conv1d_matrix_mult_filter(x, w, stride=stride, 
                                      sequence_conv=sequence_conv)
        return y
    
    def conv1d_test_setup(self, height, width, filter_width, n_filters, 
                          stride=1, sequence_conv=False):
        for dtype, err_tol in ((np.float32, self.FLOAT_ERR_TOL), 
                               (np.float64, self.DOUBLE_ERR_TOL)):
            x = curand((height, width), dtype)
            w = curand((n_filters, filter_width), dtype=dtype)
            y = self.gpu_conv1d(x, w, dtype, stride, 
                                sequence_conv=sequence_conv)
            y_np = self.cpu_conv1d(x.get(), w.get(), 
                                   stride=stride, 
                                   sequence_conv=sequence_conv)
            y_cpu = y.get()
            
            # for f in range(n_filters):
            #     err = (y_cpu[f,:,:]-y_np[f,:,:])/y_cpu[f,:,:]
            #     self.assertLess(np.linalg.norm(err, np.inf), err_tol)
            self.assertLess(np.max((y_cpu - y_np) / y_cpu), err_tol)
    
    def test_conv1d_matrix_small(self):
        for i in range(20):
            n = np.random.randint(4, 9)
            m = np.random.randint(4, 9)
            n_filters = np.random.randint(2, 5)

            self.conv1d_test_setup(n, m, 5, n_filters)

    def test_conv1d_matrix_big_height(self):
        for i in range(20):
            n = np.random.randint(200, 1000)
            m = np.random.randint(4, 9)
            n_filters = np.random.randint(2, 5)
            self.conv1d_test_setup(n, m, 5, n_filters)

    def test_conv1d_matrix_big_width(self):
        for i in range(20):
            n = np.random.randint(4, 9)
            m = np.random.randint(200, 1000)
            n_filters = np.random.randint(2, 5)            
            self.conv1d_test_setup(n, m, 5, n_filters)

    def test_conv1d_matrix_big(self):
        for i in range(20):
            n = np.random.randint(200, 1000)
            m = np.random.randint(200, 1000)
            n_filters = np.random.randint(2, 5)            
            self.conv1d_test_setup(n, m, 5, n_filters)

    def test_conv1d_matrix_big_filter(self):
        for i in range(20):
            n = np.random.randint(200, 1000)
            m = np.random.randint(200, 1000)
            w = np.random.randint(5, 15)
            n_filters = np.random.randint(2, 5)            
            self.conv1d_test_setup(n, m, w, n_filters)

    def test_conv1d_matrix_stride(self):
        for i in range(20):
            n = np.random.randint(200, 1000)
            m = np.random.randint(200, 1000)
            filter_width = 5
            n_filters = np.random.randint(2, 5)
            stride = np.random.randint(2, 5)

            for dtype, err_tol in ((np.float32, self.FLOAT_ERR_TOL), 
                                   (np.float64, self.DOUBLE_ERR_TOL)):
                x = curand((n, m), dtype)
                w = curand((n_filters, filter_width), dtype=dtype)

                y_no_stride = self.gpu_conv1d(x, w, dtype, 1)
                y_stride = self.gpu_conv1d(x, w, dtype, stride)

                for f in range(n_filters):     
                    err = (y_no_stride.get()[f,:,::stride]-
                           y_stride.get()[f,:,:])/y_no_stride.get()[f,:,::stride]
                    self.assertLess(np.linalg.norm(err, np.inf), err_tol)

    def test_conv1d_sequence(self):
        for i in range(20):
            n = np.random.randint(200, 1000)
            m = np.random.randint(200, 1000)
            w = 2*np.random.randint(2, 5)
            n_filters = np.random.randint(2, 5)            
            self.conv1d_test_setup(n, m, w, n_filters, sequence_conv=True)

class TestConvolutionGradWeights(unittest.TestCase):
    FLOAT_ERR_TOL = 1e-5
    DOUBLE_ERR_TOL = 1e-12
    
    @staticmethod
    def grad_weights_cpu(input, df_output, n_filters, filter_width,
                         sequence_conv=False):

        if not sequence_conv:
            pad = filter_width // 2;
            input_padded = np.concatenate((np.zeros((input.shape[0], pad)),
                                           input,
                                           np.zeros((input.shape[0], pad))), 1)
        else:
            input_padded = np.concatenate((input,
                                           np.zeros((input.shape[0], filter_width - 1))), 1)
        
        df_w = np.empty((n_filters, filter_width))
        for n in range(n_filters):
            for i in range(filter_width):
                df_w[n, i] = (input_padded[:,i:input.shape[1]+i]*df_output[n,:,:]).sum()
        return df_w

    def grad_weights_test(self, height, width, n_filters, filter_width, 
                          sequence_conv=False):
        for dtype, err_tol in ((np.float32, self.FLOAT_ERR_TOL),
                               (np.float64, self.DOUBLE_ERR_TOL)):
            x = curand((height, width), dtype)
            df_output = curand((n_filters, height, width), dtype)

            df_w = conv1d_grad_weights(x, df_output, filter_width, n_filters, 
                                       sequence_conv=sequence_conv)
            df_w_cpu = df_w.get()
            df_w_np = self.grad_weights_cpu(x.get(), df_output.get(), n_filters, filter_width,
                                            sequence_conv=sequence_conv)

            self.assertLess(np.linalg.norm((df_w_cpu-df_w_np)/df_w_cpu, np.inf), err_tol)

    def test_grad_weights(self):
        for n in range(20):
            n = np.random.randint(5, 300)
            m = np.random.randint(5, 1000)
            n_filters = np.random.randint(2, 100)
            filter_width = np.random.randint(1, 5)*2 + 1
            self.grad_weights_test(n, m, n_filters, filter_width)

    def test_grad_weights_sequence(self):
        for n in range(20):
            n = np.random.randint(5, 300)
            m = np.random.randint(5, 1000)
            n_filters = np.random.randint(2, 100)
            filter_width = np.random.randint(1, 5)*2
            self.grad_weights_test(n, m, n_filters, filter_width, 
                                   sequence_conv=True)

class TestMaxPool(unittest.TestCase):
    FLOAT_ERR_TOL = 1e-20
    DOUBLE_ERR_TOL = 1e-20

    @staticmethod
    def max_pool_cpu(mat, pool_size):
        output = np.empty((mat.shape[0], mat.shape[1], mat.shape[2] / pool_size))
        for n in range(output.shape[0]):
            for i in range(output.shape[2]):
                output[n,:,i] = np.max(mat[n,:, pool_size*i:pool_size*(i+1)], 1)
        return output

    def max_pool_test(self, height, width, n_filters, pool_size):
        for dtype, err_tol in ((np.float32, self.FLOAT_ERR_TOL),
                               (np.float64, self.DOUBLE_ERR_TOL)):
            mat = curand((n_filters, height, width), dtype)
            target = max_pool(mat, pool_size)
            target_cpu = target.get()
            target_np = self.max_pool_cpu(mat.get(), pool_size)
            for n in range(n_filters):
                self.assertLess(np.linalg.norm(
                    (target_cpu[n] - target_np[n]) / target_cpu[n], np.inf), 
                    err_tol)

    def test_max_pool(self):
        for i in range(20):
            height = np.random.randint(100, 1000)
            width = np.random.randint(20, 500)
            n_filters = np.random.randint(2, 10)
            pool_size = np.random.randint(2, 15)
            self.max_pool_test(height, width, n_filters, pool_size)

class TestMaxPoolGrad(unittest.TestCase):
    FLOAT_ERR_TOL = 1e-20
    DOUBLE_ERR_TOL = 1e-20

    @staticmethod
    def max_pool_grad_cpu(mat, mat_pooled, df_output, pool_size):
        df_input = np.zeros_like(mat)

        for n in range(mat.shape[0]):
            for i in range(pool_size*mat_pooled.shape[2]):
                if not i % pool_size:
                    o = df_output[n,:,i/pool_size]
                    p = mat_pooled[n,:,i/pool_size]
                df_input[n,mat[n,:,i]==p, i] = o[mat[n,:,i]==p]
        return df_input

    def max_pool_grad_test(self, height, width, n_filters, pool_size):
        for dtype, err_tol in ((np.float32, self.FLOAT_ERR_TOL),
                               (np.float64, self.DOUBLE_ERR_TOL)):
            mat = curand((n_filters, height, width), dtype)
            mat_pooled = max_pool(mat, pool_size)
            df_output = curand(mat_pooled.shape, dtype)
            df_input = max_pool_grad(mat, mat_pooled, df_output, pool_size)
            df_input_cpu = df_input.get()

            df_input_np = self.max_pool_grad_cpu(mat.get(), mat_pooled.get(), 
                                                 df_output.get(), pool_size)

            for n in range(n_filters):
                self.assertLess(
                    np.linalg.norm(df_input_cpu[0] - df_input_np[0], np.inf), 
                    err_tol)

    def test_max_pool_grad(self):
        for i in range(20):
            n = np.random.randint(100, 1000)
            m = np.random.randint(4, 500)
            n_filters = np.random.randint(2, 10)
            pool_size = np.random.randint(2, 15)
            self.max_pool_grad_test(n, m, n_filters, pool_size)
            
if __name__ == '__main__':
    unittest.main()
