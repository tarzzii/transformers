# What are the steps in conversion?



# TODO 1: Get GPT to generate the input shapes when it converts a module (not at top-level class!)
# TODO 2: Port weights from PT to TF versions and do equivalence testing
# TODO 3:

from pathlib import Path
import re
import openai
from time import sleep
from tqdm import tqdm

def get_module_name(module_text: str):
    module_name = re.search(r"(?:class |def )(\w+)", module_text).group(1)
    return module_name

def translate_fn(module_text: str):
    system_text = """
    You are a translation bot designed to translate code in the Hugging Face Transformers library from PyTorch to TensorFlow.
    
    You will be passed a single PyTorch function or class from the library. Your goal is to output the equivalent
    TensorFlow code.
    
    There are some guidelines you should follow when translating the code:
    
    - When creating layers, please pass their attribute name as the name kwarg.
    - If the class inherits from PreTrainedModel it should instead inherit from TFPreTrainedModel.
    - Retain any docstrings attached to methods like forward and translate them, even when the method is being renamed to call.
    - Layer and model classes should accept **kwargs and pass these to super.init. They should also be renamed by adding "TF" to the start of their name.
    - You don't need to import anything.
    - If the class calls other classes in the same module, please add "TF" to the start of their name if required.
    - TensorFlow layers do not require input shape arguments in the same way as PyTorch layers. As a result, the first
      argument to the constructor of layers like Dense or Conv2D (but not Embedding) can usually be removed.
    - TensorFlow Embedding layers do not have a padding_idx argument. Please remove this argument from the constructor.
    - Prefer the function shape_list(), which returns a list, over methods like tensor.shape or tf.shape(tensor).
    - Keras layers do not have a register_buffer() method. Instead just set the attribute with that name on the layer directly.
    - Output classes like BaseModelOutput or SequenceClassifierOutput should have "TF" added to the start of their name.
    - NumPy operations and calls to .numpy() must be avoided! Use TensorFlow operations instead.
    """
    module_name = get_module_name(module_text)
    if "load_tf_weights" in module_name:
        print("Skipping", module_name)
        return ""
    prompt = [{"role": "system", "content": system_text}, {"role": "user", "content": module_text}]
    for i in range(5):
        try:
            response = openai.ChatCompletion.create(model="gpt-4", messages=prompt, temperature=0, stream=True)
            break
        except openai.error.RateLimitError:
            print(f"Rate limited, retrying ({i + 1} of 5)")
            sleep(15)
    else:
        raise RuntimeError("Rate limited too many times")
    chunks = []
    for chunk in tqdm(response, desc=f"Translating {module_name}", dynamic_ncols=True, unit=" tokens"):
        chunk_message = chunk['choices'][0]['delta']
        chunks.append(chunk_message)
    translated_function = ''.join([m.get('content', '') for m in chunks])
    return translated_function


def split_file(source_file: Path):
    text = source_file.read_text()
    top_level_fns = list(re.finditer(r"\n\n((?:@|class |def ).*?)(?=\n\n@|\n\nclass |\n\ndef |$)", text, flags=re.DOTALL))
    for i in range(len(top_level_fns) - 1):
        assert top_level_fns[i].end() == top_level_fns[i + 1].start()
    preamble = text[:top_level_fns[0].start()]
    all_texts = [preamble] + [m.group(0) for m in top_level_fns]
    for i in range(len(all_texts) - 1):
        text = all_texts[i]
        if not text.endswith("\n"):
            breakpoint()
    return [text.strip() for text in all_texts]


def main():
    path = Path("src/transformers/models/gpt_neo/modeling_gpt_neo.py")
    out_path = Path("src/transformers/models/gpt_neo/modeling_tf_gpt_neo.py")
    split_fns = split_file(path)
    module_names = [get_module_name(fn) for fn in split_fns[1:]]
    module_names = [name for name in module_names if "load_tf_weights" not in name]
    translated_fns = [split_fns[0]]
    translated_fns += [translate_fn(fn) for fn in split_fns[1:]]
    output = '\n'.join(translated_fns)
    out_path.write_text(output)


if __name__ == '__main__':
    main()