# Recurrent neural network

In artificial neural networks, recurrent neural networks (RNNs) are designed for processing sequential data, such as text, speech, and time series, where the order of elements is important. Unlike feedforward neural networks, which process inputs independently, RNNs utilize recurrent connections, where the output of a neuron at one time step is fed back as input to the network at the next time step. This enables RNNs to capture temporal dependencies and patterns within sequences.
The fundamental building block of RNN is the recurrent unit, which maintains a hidden state—a form of memory that is updated at each time step based on the current input and the previous hidden state. This feedback mechanism allows the network to learn from past inputs and incorporate that knowledge into its current processing. RNNs have been successfully applied to tasks such as unsegmented, connected handwriting recognition, speech recognition, natural language processing, and neural machine translation.
However, traditional RNNs suffer from the vanishing gradient problem, which limits their ability to learn long-range dependencies. This issue was addressed by the development of the long short-term memory (LSTM) architecture in 1997, making it the standard RNN variant for handling long-term dependencies. Later, gated recurrent units (GRUs) were introduced as a more computationally efficient alternative.
In recent years, transformers, which rely on self-attention mechanisms instead of recurrence, have become the dominant architecture for many sequence-processing tasks, particularly in natural language processing, due to their superior handling of long-range dependencies and greater parallelizability. Nevertheless, RNNs remain relevant for applications where computational efficiency, real-time processing, or the inherent sequential nature of data is crucial.


## History


## Before modern
One origin of RNN was neuroscience. The word "recurrent" is used to describe loop-like structures in anatomy. In 1901, Cajal observed "recurrent semicircles" in the cerebellar cortex formed by parallel fiber, Purkinje cells, and granule cells. In 1933, Lorente de Nó discovered "recurrent, reciprocal connections" by Golgi's method, and proposed that excitatory loops explain certain aspects of the vestibulo-ocular reflex. During 1940s, multiple people proposed the existence of feedback in the brain, which was a contrast to the previous understanding of the neural system as a purely feedforward structure. Hebb considered "reverberating circuit" as an explanation for short-term memory. The McCulloch and Pitts paper (1943), which proposed the McCulloch-Pitts neuron model, considered networks that contains cycles. The current activity of such networks can be affected by activity indefinitely far in the past. They were both interested in closed loops as possible explanations for e.g. epilepsy and causalgia. Recurrent inhibition was proposed in 1946 as a negative feedback mechanism in motor control. Neural feedback loops were a common topic of discussion at the Macy conferences. See  for an extensive review of recurrent neural network models in neuroscience.
Frank Rosenblatt in 1960 published "close-loop cross-coupled perceptrons", which are 3-layered perceptron networks whose middle layer contains recurrent connections that change by a Hebbian learning rule. Later, in Principles of Neurodynamics (1961), he described "closed-loop cross-coupled" and "back-coupled" perceptron networks, and made theoretical and experimental studies for Hebbian learning in these networks, and noted that a fully cross-coupled perceptron network is equivalent to an infinitely deep feedforward network.
Similar networks were published by Kaoru Nakano in 1971, Shun'ichi Amari in 1972, and William A. Little in 1974, who was acknowledged by Hopfield in his 1982 paper.
Another origin of RNN was statistical mechanics. The Ising model was developed by Wilhelm Lenz and Ernst Ising in the 1920s as a simple statistical mechanical model of magnets at equilibrium. Glauber in 1963 studied the Ising model evolving in time, as a process towards equilibrium (Glauber dynamics), adding in the component of time.
The Sherrington–Kirkpatrick model of spin glass, published in 1975, is the Hopfield network with random initialization. Sherrington and Kirkpatrick found that it is highly likely for the energy function of the SK model to have many local minima. In the 1982 paper, Hopfield applied this recently developed theory to study the Hopfield network with binary activation functions. In a 1984 paper he extended this to continuous activation functions. It became a standard model for the study of neural networks through statistical mechanics.


## Modern
During the resurgence of neural networks in the 1980s, recurrent networks were studied again. Two influential architectures from this period were the Jordan network, proposed by Michael I. Jordan in 1986, and the Elman network, introduced by Jeffrey Elman in 1990.  
Long short-term memory (LSTM) was introduced by Sepp Hochreiter and Jürgen Schmidhuber in 1997 to address difficulties in learning long-range dependencies with recurrent networks. The same year, Mike Schuster and Kuldip K. Paliwal introduced bidirectional recurrent neural networks (BRNNs), which process a sequence in both forward and backward directions. 
Bidirectionality was subsequently combined with LSTM, and by the mid-2000s bidirectional LSTM networks had achieved strong results in speech recognition. They improved large-vocabulary speech recognition and text-to-speech synthesis and were used in Google voice search.
Recurrent networks also proved effective for language modeling. In 2010, Tomáš Mikolov and co-authors demonstrated that recurrent neural-network language models could substantially outperform conventional n-gram models. 
In 2014, Kyunghyun Cho and co-authors proposed an RNN encoder–decoder for machine translation, while another 2014 study demonstrated sequence-to-sequence learning using LSTMs. They became state of the art in machine translation, and were instrumental in the development of attention mechanisms and transformers.


## Configurations

An RNN-based model can be factored into two parts: configuration and architecture. Multiple RNNs can be combined in a data flow, and the data flow itself is the configuration. Each RNN itself may have any architecture, including LSTM, GRU, etc.


## Standard

RNNs come in many variants. Abstractly speaking, an RNN is a function 
  
    
      
        
          f
          
            θ
          
        
      
    
    {\displaystyle f_{\theta }}
  
 of type 
  
    
      
        (
        
          x
          
            t
          
        
        ,
        
          h
          
            t
          
        
        )
        ↦
        (
        
          y
          
            t
          
        
        ,
        
          h
          
            t
            +
            1
          
        
        )
      
    
    {\displaystyle (x_{t},h_{t})\mapsto (y_{t},h_{t+1})}
  
, where

  
    
      
        
          x
          
            t
          
        
      
    
    {\displaystyle x_{t}}
  
: input vector;

  
    
      
        
          h
          
            t
          
        
      
    
    {\displaystyle h_{t}}
  
: hidden vector;

  
    
      
        
          y
          
            t
          
        
      
    
    {\displaystyle y_{t}}
  
: output vector;

  
    
      
        θ
      
    
    {\displaystyle \theta }
  
: neural network parameters.
In words, it is a neural network that maps an input 
  
    
      
        
          x
          
            t
          
        
      
    
    {\displaystyle x_{t}}
  
 into an output 
  
    
      
        
          y
          
            t
          
        
      
    
    {\displaystyle y_{t}}
  
, with the hidden vector 
  
    
      
        
          h
          
            t
          
        
      
    
    {\displaystyle h_{t}}
  
 playing the role of "memory", a partial record of all previous input-output pairs. At each step, it transforms input to an output, and modifies its "memory" to help it to better perform future processing.
The illustration to the right may be misleading to many because practical neural network topologies are frequently organized in "layers" and the drawing gives that appearance. However, what appears to be layers are, in fact, different steps in time, "unfolded" to produce the appearance of layers.


## Stacked RNN
A stacked RNN, or deep RNN, is composed of multiple RNNs stacked one above the other. Abstractly, it is structured as follows
Layer 1 has hidden vector 
  
    
      
        
          h
          
            1
            ,
            t
          
        
      
    
    {\displaystyle h_{1,t}}
  
, parameters 
  
    
      
        
          θ
          
            1
          
        
      
    
    {\displaystyle \theta _{1}}
  
, and maps 
  
    
      
        
          f
          
            
              θ
              
                1
              
            
          
        
        :
        (
        
          x
          
            0
            ,
            t
          
        
        ,
        
          h
          
            1
            ,
            t
          
        
        )
        ↦
        (
        
          x
          
            1
            ,
            t
          
        
        ,
        
          h
          
            1
            ,
            t
            +
            1
          
        
        )
      
    
    {\displaystyle f_{\theta _{1}}:(x_{0,t},h_{1,t})\mapsto (x_{1,t},h_{1,t+1})}
  
.
Layer 2 has hidden vector 
  
    
      
        
          h
          
            2
            ,
            t
          
        
      
    
    {\displaystyle h_{2,t}}
  
, parameters 
  
    
      
        
          θ
          
            2
          
        
      
    
    {\displaystyle \theta _{2}}
  
, and maps 
  
    
      
        
          f
          
            
              θ
              
                2
              
            
          
        
        :
        (
        
          x
          
            1
            ,
            t
          
        
        ,
        
          h
          
            2
            ,
            t
          
        
        )
        ↦
        (
        
          x
          
            2
            ,
            t
          
        
        ,
        
          h
          
            2
            ,
            t
            +
            1
          
        
        )
      
    
    {\displaystyle f_{\theta _{2}}:(x_{1,t},h_{2,t})\mapsto (x_{2,t},h_{2,t+1})}
  
.
...
Layer 
  
    
      
        n
      
    
    {\displaystyle n}
  
 has hidden vector 
  
    
      
        
          h
          
            n
            ,
            t
          
        
      
    
    {\displaystyle h_{n,t}}
  
, parameters 
  
    
      
        
          θ
          
            n
          
        
      
    
    {\displaystyle \theta _{n}}
  
, and maps 
  
    
      
        
          f
          
            
              θ
              
                n
              
            
          
        
        :
        (
        
          x
          
            n
            −
            1
            ,
            t
          
        
        ,
        
          h
          
            n
            ,
            t
          
        
        )
        ↦
        (
        
          x
          
            n
            ,
            t
          
        
        ,
        
          h
          
            n
            ,
            t
            +
            1
          
        
        )
      
    
    {\displaystyle f_{\theta _{n}}:(x_{n-1,t},h_{n,t})\mapsto (x_{n,t},h_{n,t+1})}
  
.
Each layer operates as a stand-alone RNN, and each layer's output sequence is used as the input sequence to the layer above. There is no conceptual limit to the depth of stacked RNN.


## Bidirectional

A bidirectional RNN (biRNN) is composed of two RNNs, one processing the input sequence in one direction, and another in the opposite direction. Abstractly, it is structured as follows:
The forward RNN processes in one direction: 
  
    
      
        
          f
          
            θ
          
        
        (
        
          x
          
            0
          
        
        ,
        
          h
          
            0
          
        
        )
        =
        (
        
          y
          
            0
          
        
        ,
        
          h
          
            1
          
        
        )
        ,
        
          f
          
            θ
          
        
        (
        
          x
          
            1
          
        
        ,
        
          h
          
            1
          
        
        )
        =
        (
        
          y
          
            1
          
        
        ,
        
          h
          
            2
          
        
        )
        ,
        …
      
    
    {\displaystyle f_{\theta }(x_{0},h_{0})=(y_{0},h_{1}),f_{\theta }(x_{1},h_{1})=(y_{1},h_{2}),\dots }
  

The backward RNN processes in the opposite direction:
  
    
      
        
          f
          
            
              θ
              ′
            
          
          ′
        
        (
        
          x
          
            N
          
        
        ,
        
          h
          
            N
          
          ′
        
        )
        =
        (
        
          y
          
            N
          
          ′
        
        ,
        
          h
          
            N
            −
            1
          
          ′
        
        )
        ,
        
          f
          
            
              θ
              ′
            
          
          ′
        
        (
        
          x
          
            N
            −
            1
          
        
        ,
        
          h
          
            N
            −
            1
          
          ′
        
        )
        =
        (
        
          y
          
            N
            −
            1
          
          ′
        
        ,
        
          h
          
            N
            −
            2
          
          ′
        
        )
        ,
        …
      
    
    {\displaystyle f'_{\theta '}(x_{N},h_{N}')=(y'_{N},h_{N-1}'),f'_{\theta '}(x_{N-1},h_{N-1}')=(y'_{N-1},h_{N-2}'),\dots }
  

The two output sequences are then concatenated to give the total output: 
  
    
      
        (
        (
        
          y
          
            0
          
        
        ,
        
          y
          
            0
          
          ′
        
        )
        ,
        (
        
          y
          
            1
          
        
        ,
        
          y
          
            1
          
          ′
        
        )
        ,
        …
        ,
        (
        
          y
          
            N
          
        
        ,
        
          y
          
            N
          
          ′
        
        )
        )
      
    
    {\displaystyle ((y_{0},y_{0}'),(y_{1},y_{1}'),\dots ,(y_{N},y_{N}'))}
  
.
Bidirectional RNN allows the model to process a token both in the context of what came before it and what came after it. By stacking multiple bidirectional RNNs together, the model can process a token increasingly contextually. The ELMo model (2018) is a stacked bidirectional LSTM which takes character-level as inputs and produces word-level embeddings.


## Encoder-decoder

Two R