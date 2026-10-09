# Transformer (deep learning)

In deep learning, the transformer is a family of artificial neural network architectures based on the multi-head attention mechanism, in which input data such as text, images, or audio is  converted to a sequence of numerical representations called tokens, and each token is converted into a vector through an embedding layer. At each layer, each token is then contextualized within the scope of the context window with other (unmasked) tokens via a parallel multi-head attention mechanism, allowing the signal for key tokens to be amplified and less important tokens to be diminished. Because self-attention alone is permutation-invariant, transformers inject positional information, typically through positional encodings or learned positional embeddings, so token order can affect the output.
Because transformers do not process tokens one at a time, their computations can be parallelized across sequence positions during training more readily than those of recurrent neural networks like long short-term memory (LSTM). Later variations have been widely adopted for training large language models (LLMs) on large (language) datasets.

The original version of the transformer architecture was proposed in the 2017 paper "Attention Is All You Need" by researchers at Google. The predecessors of transformers were developed as an improvement over previous architectures for machine translation, but have found many applications since. They are used in large-scale natural language processing, computer vision (vision transformers), reinforcement learning, audio, multimodal learning, robotics, and playing chess. It has also led to the development of pre-trained systems, such as generative pre-trained transformers (GPTs).


## History


## Predecessors
Before transformers, recurrent neural networks (RNNs) were widely used for sequence modelling and generation. A well-cited early example was the Elman network (1990). In theory, the information from one token can propagate arbitrarily far down the sequence, but in practice the vanishing-gradient problem leaves the model's state at the end of a long sentence without precise, extractable information about preceding tokens.
A key breakthrough was LSTM (originally described in a 1995 technical report and formally published in 1997), an RNN that introduced gating mechanisms to mitigate the vanishing gradient problem, allowing efficient learning of long-sequence modelling. One key architectural element was the use of multiplicative gating units, in which the outputs of some neurons modulate the outputs of others. These multiplicative units are conceptually distinct from the additive attention mechanism later introduced for sequence-to-sequence models.
 Neural networks using multiplicative units were later called sigma-pi networks or higher-order networks. LSTM became the standard architecture for long sequence modelling until the 2017 publication of transformers. However, LSTM still used sequential processing, like most other RNNs. Specifically, RNNs operate one token at a time from first to last; they cannot operate in parallel over all tokens in a sequence.
Transformers allow parallel processing of tokens during training, but standard self-attention has computational and memory costs that grow quadratically with sequence length. The fast weight controller, proposed in 1992, used one network to generate input-dependent weights for another network. This method built on earlier work on "fast weights" and "dynamic links". A slow neural network learns by gradient descent to generate keys and values for computing the weight changes of the fast neural network which computes answers to queries. This was later shown to be equivalent to the unnormalized linear transformer.


## Attention with seq2seq

The idea of encoder–decoder sequence transduction had been developed in the early 2010s; commonly cited as the originators that produced seq2seq are two concurrently published papers from 2014.
A 380M-parameter model for machine translation uses two long short-term memories (LSTM). Its architecture consists of two parts. The encoder is an LSTM that takes in a sequence of tokens and turns it into a vector. The decoder is another LSTM that converts the vector into a sequence of tokens. Similarly, another 130M-parameter model used gated recurrent units (GRU) instead of LSTM. Later research showed that GRUs are neither better nor worse than LSTMs for seq2seq.
These early seq2seq models had no attention mechanism, and the state vector is accessible only after the last word of the source text was processed. Although in theory such a vector retains the information about the whole original sentence, in practice the information is poorly preserved. This is because the input is processed sequentially by one recurrent network into a fixed-size output vector, which is then processed by another recurrent network into an output. If the input is long, then the output vector would not be able to contain all relevant information, degrading the output. As evidence, reversing the input sentence improved seq2seq translation.
The RNN search model introduced an attention mechanism to seq2seq for machine translation to solve the bottleneck problem (of the fixed-size output vector), allowing the model to process long-distance dependencies more easily. The name is because it "emulates searching through a source sentence during decoding a translation".
The relative performances were compared between global (that of RNN search) and local (sliding window) attention model architectures for machine translation, finding that mixed attention had higher quality than global attention, while local attention reduced translation time.
In 2016, Google Translate was revamped to Google Neural Machine Translation, which replaced the previous model based on statistical machine translation. The new model was a seq2seq model where the encoder and the decoder were both 8 layers of bidirectional LSTM. It took nine months to develop, and it outperformed the statistical approach, which took ten years to develop.


## Parallelizing attention

Seq2seq models with attention (including self-attention) still suffered from the same issue with recurrent networks, which is that they are hard to parallelize, which prevented them from being accelerated on GPUs. In 2016, decomposable attention applied a self-attention mechanism to feedforward networks, which are easy to parallelize, and achieved state-of-the-art (SOTA) results in textual entailment with an order of magnitude fewer parameters than LSTMs. One of its authors, Jakob Uszkoreit, suspected that attention without recurrence would be sufficient for language translation, thus the title "attention is All you need". That hypothesis was against conventional wisdom at the time, and even his father Hans Uszkoreit, a well-known computational linguist, was skeptical. In the same year, self-attention (called intra-attention or intra-sentence attention) was proposed for LSTMs.
On 2017-06-12, the original (100M-parameter) encoder–decoder transformer model was published in the "Attention is All you need" paper. At the time, the focus of the research was on improving seq2seq for machine translation, by removing its recurrence to process all tokens in parallel, but preserving its dot-product attention mechanism to keep its text processing performance. This led to the introduction of a multi-head attention model that was easier to parallelize due to the use of independent heads and the lack of recurrence. Its parallelizability was an important factor to its widespread use in large neural networks.


## AI boom era

In spring 2017, before the "Attention is All you need" preprint was published, one of the co-authors applied the "decoder-only" variation of the architecture to generate fictitious Wikipedia articles. Transformer architecture is now used alongside many generative models that contribute to the ongoing AI boom.
The "reference implementation" of the original Transformer was written in a TensorFlow library. In language modelling, ELMo (2018) was a bi-directional LSTM that produces contextualized word embeddings, improving upon the line of research from bag of words and word2vec. It was followed by BERT (2018), an encoder-only transformer model. In October 2019, Google started using BERT to process search queries. In 2020, Google Translate replaced the previous RNN-encoder–RNN-decoder model by a transformer-encoder–RNN-decoder model.
Starting in 2018, the OpenAI GPT series of decoder-only transformers became state of the art in natural language generation. At the end of 2022, ChatGPT, a chatbot based on a fine-tuned variant of GPT-3.5, became unexpectedly popular, triggering a boom around large language models.
Transformers have been applied in modalities beyond text. Four days after the publication of "Attention is All You Need", a multimodal transformer architecture, MultiModel, was published by most authors of that paper. Other examples include the vision transformer, which has led to developments in convolutional neural networks. Image and video generators like DALL-E (2021), Stable Diffusion 3 (2024), and Sora (2024), use transformers to analyse input data (like text prompts) by breaking it down into "tokens" and then calculating the relevance between each token using self-attention, which helps the model simulate the context and relationships within the data.


## Training


## Methods for stabilizing training
The plain transformer architecture had difficulty in converging. In the original paper, the authors recommended using learning rate warmup. That is, the learning rate should linearly scale up from 0 to maximal value for the first part of the training (usually recommended to be 2% of the total number of training steps), before decaying again.
A 2020 paper found that using layer normalization before (instead of after) multihead attention and feedforward layers stabilizes training, not requiring learning rate warmup. This is the "pre-LN Transformer" and is more commonly used, compared to the original "post-LN Transformer".


## Regularization
The original transformer used dropout during training to reduce overfitting. Dropout was applied to the output of each sublayer before its residual connection and normalization, as well as to the sums of token embeddings and positional encodings. The original paper also used label smoothing, which replaces a certain target distribution with one that assigns a small amount of probability to alternative tokens. These techniques can improve generalization by going against overconfidence in the training targets.


## Distributed Training
Large transformer models are typically trained across multiple GPUs or other accelerators because their parameters, activations, and training data may not fit on a single device. Data parallelism copies the model across devices and splits different batches of training examples among them; gradients are then synchronized before parameters are updated. Model parallelism divides a model itself across devices. Tensor parallelism splits operations within individual layers, while pipeline parallelism assigns consecutive groups of layers to different devices.


## Pretrain-finetune
Transformers typically are first pretrained by self-supervised learning on a large generic dataset, followed by supervised fine-tuning on a small task-specific dataset. The pretrain dataset is typically an unlabeled large corpus, such as The Pile. Tasks for pretraining and fine-tuning commonly include:

reading comprehension
sentiment analysis
paraphrasing
The T5 transformer report documents a large number of natural language pretraining tasks. Some examples are:

restoring or repairing incomplete or corrupted text. For example, the input, "Thank you ~~ me to your party ~~ week", might generate the output, "Thank you for inviting me to your party last week".
translation between natural languages (machine translation)
judging the pragmatic acceptability of natural language. For example, the following sentence might be judged "not acceptable", because even though it is syntactically well-formed, it is improbable in ordinary human usage: The course is jumping well.
While each of these tasks is trivial or obvious for human native speakers of the language (or languages), they have typically proved challenging for previous generations of machine learning architecture.


## Knowledge distillation

Knowledge distillation is a method for training a smaller model, called a "student", to reproduce the output behavior of a larger "teacher" model. In transformer models, the student can be trained using the teacher's output probability distribution, intermediate representations, or attention patterns in addition to the original training labels. Distillation can lower computational and memory requirements of deployment while keeping most of the teacher model's performance on a specified task.


## Tasks

In general, there are three classes of language modelling tasks: "masked", "autoregressive", and "prefixLM". These classes are independent of a specific modeling architecture such as transformer, but they are often discussed in the context of transformer.
In a masked task, one or more of the tokens is masked out, and the model would produce a probability distribution predicting what the masked-out tokens are based on the context. The loss function for the task is typically sum of log-perplexities for the masked-out tokens: 
  
    
      
        
          Loss
        
        =
        −
        
          ∑
          
            t
            ∈
            
              masked tokens
            
          
        
        ln
        ⁡
        (
        
          probability of 
        
        t
        
           conditional on its context
        
        )
      
    
    {\displaystyle {\text{Loss}}=-\sum _{t\in {\text{masked tokens}}}\ln({\text{probability of }}t{\text{ conditional on its context}})}
  
and the model is trained to minimize this loss function. The BERT series of models are trained for masked token prediction and another task. ("Masked" as in "masked language modelling" is not "masked" as in "masked attention".)
In an autoregressive task, the entire sequence is masked at first, and the model produces a probability distribution for the first token. Then the first token is revealed and the model predicts the second token, and so on. The loss function for the task is still typically the same. The GPT series of models are trained by autoregressive tasks.
In a prefixLM task, the sequence is divided into two parts. The first part is presented as context, and the model predicts the first token of the second part. Then that would be revealed, and the model predicts the second token, and so on. The loss function for the task is still typically the same. The T5 series of models are trained by prefixLM tasks. ("PrefixLM" as in "prefix language modeling" is not "prefixLM" as in "prefix language model".)


## Architecture

All transformers have the same primary components:

Tokenizers, which convert text into tokens.
Embedding layer, which converts tokens and positions of the tokens into vector representations.
Transformer layers, which carry out repeated transformations on the vector representations, extracting more and more linguistic information. These consist of alternating attention and feedforward layers. There are two major types of transformer layers: encoder layers and decoder layers, with further variants.
Un-embedding layer, which converts the final vector representations back to a probability distribution over the tokens.
The following description follows exactly the transformer as described in the original paper. There are variants, described in the following section.
By convention, we write all vectors as row vectors. For example, pushing a vector through a linear layer means multiplying it by a weigh