""" Speech Sentiment Audio Models"""
import os
import time
import warnings
import h5py
import pandas as pd
import pickle
import librosa
import librosa.display
from utils.speech_feature_extraction import *

from tensorflow.keras.models import load_model

print(h5py.__version__)

warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.simplefilter(action='ignore', category=UserWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="absl")
VERSION = 4
RANDOM_SEED = 7


# Load feature name lists
df_joint_train_aug = pd.read_csv('./files/feature_name_load.csv', low_memory=False)
feature_column_names = [i for i in df_joint_train_aug.columns\
                        if i not in ['file_path','renamed_file_path','split',
                                     'sentiment_value','emotional_category']]


def generate_selected_features_by_type(feature_column_names, input, stats, number=1):
    """ Generate selected features by config """
    selected_result = []
    for name in feature_column_names:
        if input + "_" + stats in name:
            selected_result.append(name)
    if number < len(selected_result):
        selected_result = selected_result[:number]
    return selected_result


# example to take mfcc 20 mean & std; mel32; zcr all 5 stats features
feature_MFCC20_mean = generate_selected_features_by_type(feature_column_names, "mfcc", "mean", 20)
feature_MFCC20_std = generate_selected_features_by_type(feature_column_names, "mfcc", "std", 20)
feature_mel32_median = generate_selected_features_by_type(feature_column_names, "mel32", "median", 32)
feature_mel32_std = generate_selected_features_by_type(feature_column_names, "mel32", "std", 32)
feature_zcr_stats = generate_selected_features_by_type(feature_column_names, "zcr", "", 5)
feature_rms_stats = generate_selected_features_by_type(feature_column_names, "rms", "", 5)
selected_spect = ['Spectrum_band_energy_difference', 'Spectrum_band_density_difference',
                  'Spectrum_center_of_gravity_spectrum', 'Spectrum_skewness_spectrum', 'Spectrum_kurtosis_spectrum',
                  'Spectrum_stddev_spectrum', 'Spectrum_band_density', 'Spectrum_band_energy']
selected_formant = ['Formant_f1_mean', 'Formant_f1_median', 'Formant_f3_mean', 'Formant_fitch_vtl', 'Formant_mff',
                    'Formant_formant_dispersion']
selected_pitch = ['Pitch_pitch_slope_without_octave_jumps', 'Pitch_q3_pitch', 'Pitch_stddev_pitch',
                  'Pitch_mean_absolute_pitch_slope', 'Pitch_mean_pitch', 'Pitch_max_pitch', 'Pitch_q1_pitch',
                  'Pitch_min_pitch']
selected_intensity = ['Intensity_max_intensity', 'Intensity_q3_intensity', 'Intensity_median_intensity',
                      'Intensity_mean_intensity', 'Intensity_stddev_intensity', 'Intensity_relative_max_intensity_time']
selected_HNR = ['HNR_stddev_hnr', 'HNR_mean_hnr', 'HNR_relative_min_hnr_time', 'HNR_max_hnr']
selected_prosody = selected_intensity + selected_pitch  # + ['Local Jitter','Local Shimmer']
selected_feature_names131 = feature_MFCC20_mean + feature_MFCC20_std + feature_mel32_median + feature_mel32_std + \
                            feature_rms_stats + selected_intensity + selected_pitch + selected_spect

selected_feature_names128 = feature_MFCC20_mean + feature_MFCC20_std + feature_mel32_median + feature_mel32_std + \
                            feature_zcr_stats + feature_rms_stats + selected_intensity + selected_pitch

selected_feature_name = selected_feature_names128
len(selected_feature_name)
# Important Note: define the selected feature names same as trained model!!!
# print(selected_feature_name)

"""### Load Model """
model_file_dir = './models'
NCS_SEN_CNN_MODEL = load_model("./models/NCS_SEN_CNN_T2_S1S3S2Aa_1008-BG6-7907.h5", compile=False)
NCA_LAN_MLP_MODEL = load_model("./models/NCS_LAN_MLP_V2_0916-A2-9722.h5", compile=False)

def load_pickle_model(model_file_dir):
    """ load pickle models from directory: for HistGradBoost, Random Forest etc. """
    if not os.path.exists(model_file_dir):
        raise FileNotFoundError(f"Model file not found at: {model_file_dir}")
    try:
        with open(model_file_dir, 'rb') as file:
            return pickle.load(file)
    except Exception as e:
        raise Exception(f"Error loading model from file: {model_file_dir}. Error: {e}")


# HGB_CLS_MODEL = load_pickle_model(f"{model_file_dir}/HistGradientBoostingClassifier_model_3cls_128feat_75acc.pkl")
RF_CLS_MODEL = load_pickle_model(f"{model_file_dir}/RandomForestClassifier_model_3cls_128feat_74acc.pkl")
LGBM_CLS_MODEL = load_pickle_model(f"{model_file_dir}/LGBMClassifier_model_3cls_128feat_82acc.pkl")

def pickle_model_predict(model_cls, test_instance):
    """ inference using pickle model by probability """
    cls_sign_map = {'neutral': 0, 'positive': 1, 'negative': -1}
    try:
        instance_input = np.array(test_instance).reshape(1, -1)
        # Check if there are any NaN values in the instance input
        if np.isnan(instance_input).any():
            print("ERROR:model_predicate: Audio model predict - Skipping prediction due to NaN values in test instance.")
            return 0, 0
        pred_cls = model_cls.predict(instance_input)[0]
        predictions_proba = model_cls.predict_proba(instance_input)
        max_prob = np.round(predictions_proba.max(axis=1), 4)[0]
        # print("[pickle CLS MODEL]: ", pred_cls)
        pred_score = max_prob * cls_sign_map[pred_cls]
        return max_prob, pred_score
    except Exception as e:
        raise Exception(f"Error during model prediction: {e}")


# region load Data
def get_stats_from_feature(feature_input):
    feature_mean, feature_median = np.mean(feature_input.T, axis=0), np.median(feature_input.T, axis=0)
    feature_std = np.std(feature_input.T, axis=0)
    feature_p10, feature_p90 = np.percentile(feature_input.T, 10, axis=0), np.percentile(feature_input.T, 90, axis=0)
    return np.concatenate((feature_mean, feature_median, feature_std, feature_p10, feature_p90), axis=0)


def calc_feature_all(filename):
    """ only for testing function """
    sample_rate_set = 16000
    X_full, sample_rate = librosa.load(filename, sr=sample_rate_set)

    # 获取音频的实际时长
    audio_duration = librosa.get_duration(y=X_full, sr=sample_rate)
    # print(f"Audio duration for {filename}: {audio_duration:.2f} seconds")

    # 丢弃小于 0.128 秒的音频文件
    if audio_duration < 0.128:
        # print(f"Skipping file {filename} because it is too short (<0.128s).")
        return

    # 如果音频小于 0.2 秒，设置 duration_to_use 为 0.2 秒，否则使用实际时长
    duration_to_use = max(audio_duration, 0.2)

    # 加载音频文件，使用调整后的时长
    X, sample_rate = librosa.load(filename, res_type='kaiser_fast', duration=duration_to_use, sr=sample_rate_set,
                                  offset=0)

    # 检查音频是否为空
    if len(X) == 0:
        # print(f"Skipping file {filename} because it is empty.")
        return

    mfccs_60 = librosa.feature.mfcc(y=X, sr=sample_rate, n_mfcc=20)
    feature_mfccs_60_stats = get_stats_from_feature(mfccs_60)
    stft = np.abs(librosa.stft(X))
    feature_mel_32_stats = get_stats_from_feature(librosa.feature.melspectrogram(y=X, sr=sample_rate,
                                                                                 n_fft=2048, hop_length=512,
                                                                                 n_mels=32, fmax=8000))
    feature_zcr_stats = get_stats_from_feature(librosa.feature.zero_crossing_rate(y=X))
    feature_rms_stats = get_stats_from_feature(librosa.feature.rms(y=X))
    features = np.concatenate((feature_mfccs_60_stats,
                               feature_mel_32_stats,
                               feature_zcr_stats,
                               feature_rms_stats
                               ), axis=0)
    # Define Feature Naming updated at 20240916
    prefixes = {'mfcc': 20, 'mel32': 32, 'zcr': 1, 'rms': 1}
    column_names = []
    for prefix, num_features in prefixes.items():
        for prefix_stats in ['mean', 'median', 'std', 'p10', 'p90']:
            if num_features > 1:
                column_names.extend([f'{prefix}_{prefix_stats}_{i}' for i in range(1, num_features + 1)])
            else:
                column_names.append(f'{prefix}_{prefix_stats}')

    assert len(column_names) == 5 * (20 + 32 + 2)

    feature_part1 = {}
    for key, value in zip(column_names, features):
        feature_part1[key] = value

    sound = parselmouth.Sound(values=X, sampling_frequency=sample_rate, start_time=0)
    intensity_attributes = get_intensity_attributes(sound)[0]
    pitch_attributes = get_pitch_attributes(sound)[0]
    spectrum_attributes = get_spectrum_attributes(sound)[0]
    expanded_intensity_attributes = {f"Intensity_{key}": value for key, value in intensity_attributes.items()}
    expanded_pitch_attributes = {f"Pitch_{key}": value for key, value in pitch_attributes.items()}
    expanded_spectrum_attributes = {f"Spectrum_{key}": value for key, value in spectrum_attributes.items()}

    feature_prosody = {
        **expanded_intensity_attributes,  # Unpack expanded intensity attributes
        **expanded_pitch_attributes,  # Unpack expanded pitch attributes
        **expanded_spectrum_attributes,  # Unpack expanded spectrum attributes
    }
    feature_combined = {**feature_part1, **feature_prosody}
    # print("feature_combined:",feature_combined)
    return feature_combined


def calc_feature_all_from_binary(x: np.ndarray):
    """ feature calculation for streaming signals """
    sample_rate = 16000

    mfccs_20 = librosa.feature.mfcc(y=x, sr=sample_rate, n_mfcc=20)
    feature_mfccs_20_stats = get_stats_from_feature(mfccs_20)
    stft = np.abs(librosa.stft(x))
    feature_mel_32_stats = get_stats_from_feature(librosa.feature.melspectrogram(y=x, sr=sample_rate,
                                                                                 n_fft=2048, hop_length=512,
                                                                                 n_mels=32, fmax=8000))
    feature_zcr_stats = get_stats_from_feature(librosa.feature.zero_crossing_rate(y=x))
    feature_rms_stats = get_stats_from_feature(librosa.feature.rms(y=x))
    features = np.concatenate((feature_mfccs_20_stats,
                               feature_mel_32_stats,
                               feature_zcr_stats,
                               feature_rms_stats
                               ), axis=0)
    prefixes = {'mfcc': 20, 'mel32': 32, 'zcr': 1, 'rms': 1}
    column_names = []
    for prefix, num_features in prefixes.items():
        for prefix_stats in ['mean', 'median', 'std', 'p10', 'p90']:
            if num_features > 1:
                column_names.extend([f'{prefix}_{prefix_stats}_{i}' for i in range(1, num_features + 1)])
            else:
                column_names.append(f'{prefix}_{prefix_stats}')

    assert len(column_names) == 5 * (20 + 32 + 2)

    feature_part1 = {}
    for key, value in zip(column_names, features):
        feature_part1[key] = value

    sound = parselmouth.Sound(values=x, sampling_frequency=sample_rate, start_time=0)
    intensity_attributes = get_intensity_attributes(sound)[0]
    pitch_attributes = get_pitch_attributes(sound)[0]
    spectrum_attributes = get_spectrum_attributes(sound)[0]
    expanded_intensity_attributes = {f"Intensity_{key}": value for key, value in intensity_attributes.items()}
    expanded_pitch_attributes = {f"Pitch_{key}": value for key, value in pitch_attributes.items()}
    expanded_spectrum_attributes = {f"Spectrum_{key}": value for key, value in spectrum_attributes.items()}

    feature_prosody = {
        **expanded_intensity_attributes,  # Unpack expanded intensity attributes
        **expanded_pitch_attributes,  # Unpack expanded pitch attributes
        **expanded_spectrum_attributes,  # Unpack expanded spectrum attributes
    }
    feature_combined = {**feature_part1, **feature_prosody}
    # print("feature_combined:",feature_combined)
    return feature_combined

def preprocess_signal(x_input):
    """ check duration and do padding """
    sample_rate = 16000  # Example sample rate
    min_duration_sec = 0.2  # Minimum duration in seconds
    min_duration_samples = int(min_duration_sec * sample_rate)  # Convert to samples
    max_duration_sec = 5  # Max duration in seconds
    max_duration_samples = int(max_duration_sec * sample_rate)  # Convert to samples

    # check input if is empty
    if len(x_input) == 0:
        # print(f"Skipping because input is empty.")
        return

    # get duration
    audio_duration = librosa.get_duration(y=x_input, sr=sample_rate)
    # print(f"Audio duration for : {audio_duration:.2f} seconds")
    # dump if <0.128 too short
    if audio_duration < 0.128:
        # print(f"Skipping because input is too short (<0.128s).")
        return
    if audio_duration > 5:
        # print(f"[WARNING] input binary signal last more than 5 seconds.")
        pass

    # Determine the number of samples in the current audio
    current_samples = len(x_input)
    # If the audio is shorter than the minimum duration, pad it with zeros
    if current_samples < min_duration_samples:
        padding_samples = min_duration_samples - current_samples
        # Pad with zeros at the end of the audio signal
        x = np.pad(x_input, (0, padding_samples), mode='constant')
        # print(f"Audio was padded to {min_duration_sec} seconds")
    elif current_samples > max_duration_samples:
        x = x_input[:max_duration_samples]
    else:
        x = x_input  # No padding needed

    return x

# endregion


def audio_model_inference(x_input: np.ndarray):
    """
    main function to run inference - configurable to improve performance
    TODO: ensemble methods on top of models
    """
    try:
        start = time.time()
        x = preprocess_signal(x_input)
        feature_test_instance = calc_feature_all_from_binary(x)
        test_instance = [feature_test_instance[key] for key in selected_feature_name if key in feature_test_instance]
        if not feature_test_instance:
            print("[ATTENTION] - feature_test_instance is none:")
            return None, None
        # print("[TIME] - Feature Extraction takes {:.2f} seconds".format(time.time() - start))
        # Phase 1
        # final_score = calculate_final_score(test_instance)
        # this semester score - replace [-1,0,1] with scaled max_prob * [-1,0,1]
        sentiment_class_CNN, sentiment_score_CNN = CNN_Model_Predication_New(test_instance)
        sentiment_max_prob_RF, sentiment_score_RF = pickle_model_predict(RF_CLS_MODEL,test_instance)
        sentiment_max_prob_LGBM, sentiment_score_LGBM = pickle_model_predict(LGBM_CLS_MODEL, test_instance)
        # print("[TIME] - Audio models takes {:.2f} seconds".format(time.time() - start))
        combine_score = (sentiment_score_CNN + sentiment_score_RF + sentiment_score_LGBM)/3
        # max_abs_score = max(abs([sentiment_score_CNN, sentiment_score_RF, sentiment_score_LGBM])) # TODO
        # print("[SCORE] CNN {:.2f}   RF {:.2f}   LGBM {:.2f}   final {:.2f}".format(
        #     sentiment_score_CNN, sentiment_score_RF, sentiment_score_LGBM, combine_score))
        sentiment_category = determine_sentiment_category(combine_score)
        # print("[TIME] - takes {:.2f} seconds".format(time.time() - start))
        if isinstance(combine_score, (int, float)):  # Check if it's an int or float
            return float(combine_score), sentiment_category
        else:
            return None, None
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e} at audio_model_inference()")
        return None, None


"""## CNN Model Predication"""
def CNN_Model_Predication_New(test_instance):
    model = NCS_SEN_CNN_MODEL
    X_test = test_instance
    X_test_cnn = np.expand_dims(X_test, axis=0).astype(np.float32)

    # Get the predicted probabilities from the softmax layer
    y_pred_probs = model.predict(X_test_cnn, verbose=0)
    # print("Softmax probabilities:", y_pred_probs)
    y_pred = np.argmax(y_pred_probs, axis=-1)
    # y_pred_coefficient = np.interp(np.max(y_pred_probs), (0.2, 0.7), (0, 1))
    # y_pred = np.argmax(model.predict(X_test_cnn, verbose=0), axis=-1)

    if y_pred == 0:
        sentiment_class_3_new = -1
    elif y_pred == 1:
        sentiment_class_3_new = 0
    elif y_pred == 2:
        sentiment_class_3_new = 1
    # print("this semester CNN Model output:", sentiment_class_3_new)
    return sentiment_class_3_new, round(np.max(y_pred_probs) * sentiment_class_3_new, 4)


# region score mapping and weightages aggregation
# determine sentiment category based on combine score
def determine_sentiment_category(combine_score):
    sentiment_category = "Neutral sentiment"  # default Neutral
    if combine_score < -0.3:
        sentiment_category = "Negative sentiment"
    elif -0.3 <= combine_score <= 0.3:
        sentiment_category = "Neutral sentiment"
    elif combine_score > 0.3:
        sentiment_category = "Positive sentiment"
    # print("determine sentiment category:", sentiment_category)
    return sentiment_category

# endregion
