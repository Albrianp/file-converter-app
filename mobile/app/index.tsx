import { useState } from 'react';
import { StyleSheet, Text, View, TouchableOpacity, Alert, ActivityIndicator, ScrollView, TextInput, ImageBackground } from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import * as MediaLibrary from 'expo-media-library';

// GANTI dengan URL Railway kamu
const API_URL = process.env.EXPO_PUBLIC_API_URL || 'https://file-converter-app-production-9221.up.railway.app';

type Mode = 'upload' | 'url';

const AUDIO_FORMATS = ['mp3', 'wav', 'm4a', 'ogg'];
const VIDEO_FORMATS = ['mp4', 'avi', 'mov', 'webm'];

export default function HomeScreen() {
  const [mode, setMode] = useState<Mode>('url');
  const [selectedFile, setSelectedFile] = useState<DocumentPicker.DocumentPickerAsset | null>(null);
  const [videoUrl, setVideoUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingText, setLoadingText] = useState('Memproses...');
  const [loadingProgress, setLoadingProgress] = useState(0);
  const [targetFormat, setTargetFormat] = useState('mp3');

  const pickFile = async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: '*/*',
        copyToCacheDirectory: true,
      });

      if (!result.canceled) {
        setSelectedFile(result.assets[0]);
      }
    } catch (error: any) {
      Alert.alert('Error', 'Gagal memilih file: ' + error.message);
    }
  };

  const saveToLibrary = async (filePath: string, format: string) => {
    setLoading(false);
    setLoadingProgress(0);

    try {
      const { status } = await MediaLibrary.requestPermissionsAsync();

      if (status !== 'granted') {
        Alert.alert(
          'Izin diperlukan',
          'Aktifkan izin penyimpanan di Settings untuk menyimpan file.'
        );
        await Sharing.shareAsync(filePath);
        return;
      }

      const asset = await MediaLibrary.createAssetAsync(filePath);
      const albumName = 'FreeDownloader';
      const existingAlbum = await MediaLibrary.getAlbumAsync(albumName);

      if (existingAlbum) {
        await MediaLibrary.addAssetsToAlbumAsync([asset], existingAlbum, false);
      } else {
        await MediaLibrary.createAlbumAsync(albumName, asset, false);
      }

      Alert.alert('✅ Berhasil', `File tersimpan di album "${albumName}"`);
    } catch (e: any) {
      await Sharing.shareAsync(filePath);
    }
  };

  const convertFile = async () => {
    if (!selectedFile) {
      Alert.alert('Pilih file dulu', 'Silakan pilih file audio/video terlebih dahulu');
      return;
    }

    setLoading(true);
    setLoadingProgress(20);
    setLoadingText('Mengupload file...');

    try {
      const outputPath = `${FileSystem.cacheDirectory}converted_${Date.now()}.${targetFormat}`;

      // Upload file dan langsung stream response ke disk
      const uploadResult = await FileSystem.uploadAsync(
        `${API_URL}/convert/media?target_format=${targetFormat}`,
        selectedFile.uri,
        {
          httpMethod: 'POST',
          uploadType: FileSystem.FileSystemUploadType.MULTIPART,
          fieldName: 'file',
          mimeType: selectedFile.mimeType || 'application/octet-stream',
        }
      );

      setLoadingProgress(70);
      setLoadingText('Menyimpan file...');

      if (uploadResult.status !== 200) {
        throw new Error(`Server error: ${uploadResult.status}`);
      }

      // Simpan response body (base64) ke file
      await FileSystem.writeAsStringAsync(outputPath, uploadResult.body, {
        encoding: FileSystem.EncodingType.Base64,
      });

      setLoadingProgress(100);
      await saveToLibrary(outputPath, targetFormat);
    } catch (error: any) {
      setLoading(false);
      setLoadingProgress(0);
      Alert.alert('Konversi Gagal', error.message);
    }
  };

  const downloadFromUrl = async () => {
    if (!videoUrl.trim()) {
      Alert.alert('URL kosong', 'Silakan masukkan URL video terlebih dahulu');
      return;
    }

    if (!isValidUrl(videoUrl)) {
      Alert.alert(
        'Link tidak valid',
        'Pastikan link diawali dengan http:// atau https:// dan merupakan link yang lengkap'
      );
      return;
    }

    setLoading(true);
    setLoadingProgress(0);
    setLoadingText('Menghubungkan ke server...');

    const progressStages = [
      { at: 1500, text: 'Mengambil informasi video...' },
      { at: 4000, text: 'Mengunduh video dari platform...' },
      { at: 15000, text: 'Mengunduh video...\nVideo panjang butuh waktu lebih lama' },
      { at: 30000, text: 'Mengkonversi ke format target...' },
      { at: 45000, text: 'Hampir selesai, mohon tunggu...' },
    ];

    const timers = progressStages.map((stage) =>
      setTimeout(() => setLoadingText(stage.text), stage.at)
    );

    const progressInterval = setInterval(() => {
      setLoadingProgress((prev) => (prev < 88 ? prev + 1.5 : prev));
    }, 1000);

    const cleanup = () => {
      timers.forEach(clearTimeout);
      clearInterval(progressInterval);
    };

    try {
      const outputPath = `${FileSystem.cacheDirectory}downloaded_${Date.now()}.${targetFormat}`;

      const encodedUrl = encodeURIComponent(videoUrl.trim());
      const downloadUrl = `${API_URL}/download/url?url=${encodedUrl}&target_format=${targetFormat}`;

      // Stream response langsung ke file di disk pakai GET
      const downloadResult = await FileSystem.downloadAsync(
        downloadUrl,
        outputPath
      );

      cleanup();

      if (downloadResult.status !== 200) {
        throw new Error(`Server error: ${downloadResult.status}`);
      }

      setLoadingProgress(100);
      setLoadingText('Menyimpan file...');

      await saveToLibrary(outputPath, targetFormat);
    } catch (error: any) {
      cleanup();
      setLoading(false);
      setLoadingProgress(0);
      Alert.alert('Download Gagal', error.message);
    }
  };

  const switchMode = (newMode: Mode) => {
    setMode(newMode);
    setSelectedFile(null);
    setVideoUrl('');
  };

  const isValidUrl = (text: string) => {
    try {
      const parsed = new URL(text.trim());
      return parsed.protocol === 'http:' || parsed.protocol === 'https:';
    } catch {
      return false;
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.scrollContent}>
      {/* Hero dengan foto background */}
      <ImageBackground
        source={require('../assets/images/bg1.jpg')}
        style={styles.hero}
        imageStyle={styles.heroImage}
      >
        <View style={styles.heroOverlay} />

        <View style={styles.heroContent}>
          <View style={styles.logoRow}>
            <View style={styles.logoBox}>
              <Text style={styles.logoIcon}>↓</Text>
            </View>
            <Text style={styles.logoText}>FreeDownloader</Text>
          </View>

          <Text style={styles.heroLabel}>Online video dan audio</Text>
          <Text style={styles.heroTitle}>Download apa saja{'\n'}dari satu link</Text>

          {/* Tab Mode */}
          <View style={styles.tabRow}>
            <TouchableOpacity
              style={[styles.tab, mode === 'url' && styles.tabActive]}
              onPress={() => switchMode('url')}
            >
              <Text style={[styles.tabText, mode === 'url' && styles.tabTextActive]}>
                Dari URL
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.tab, mode === 'upload' && styles.tabActive]}
              onPress={() => switchMode('upload')}
            >
              <Text style={[styles.tabText, mode === 'upload' && styles.tabTextActive]}>
                Upload file
              </Text>
            </TouchableOpacity>
          </View>

          {mode === 'url' ? (
            <View style={styles.urlBar}>
              <TextInput
                style={styles.urlInput}
                placeholder="Tempel link video di sini..."
                placeholderTextColor="#999"
                value={videoUrl}
                onChangeText={setVideoUrl}
                autoCapitalize="none"
                autoCorrect={false}
              />
            </View>
          ) : (
            <TouchableOpacity style={styles.uploadBar} onPress={pickFile}>
              <Text style={styles.uploadBarText} numberOfLines={1}>
                {selectedFile ? selectedFile.name : 'Pilih file audio/video...'}
              </Text>
            </TouchableOpacity>
          )}
        </View>
      </ImageBackground>

      {/* Body Section */}
      <View style={styles.body}>
        <Text style={styles.sectionLabel}>Convert ke format</Text>

        <Text style={styles.formatGroupLabel}>Audio</Text>
        <View style={styles.formatGrid}>
          {AUDIO_FORMATS.map((format) => (
            <TouchableOpacity
              key={format}
              style={[styles.formatButton, targetFormat === format && styles.formatButtonActive]}
              onPress={() => setTargetFormat(format)}
            >
              <Text style={[styles.formatButtonText, targetFormat === format && styles.formatButtonTextActive]}>
                {format.toUpperCase()}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={styles.formatGroupLabel}>Video</Text>
        <View style={styles.formatGrid}>
          {VIDEO_FORMATS.map((format) => (
            <TouchableOpacity
              key={format}
              style={[styles.formatButton, targetFormat === format && styles.formatButtonActive]}
              onPress={() => setTargetFormat(format)}
            >
              <Text style={[styles.formatButtonText, targetFormat === format && styles.formatButtonTextActive]}>
                {format.toUpperCase()}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <TouchableOpacity
          style={[styles.convertButton, loading && styles.convertButtonDisabled]}
          onPress={mode === 'upload' ? convertFile : downloadFromUrl}
          disabled={loading}
        >
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.convertButtonText}>
              {mode === 'upload' ? 'Convert sekarang' : 'Download & convert'}
            </Text>
          )}
        </TouchableOpacity>

        {loading && (
          <View style={styles.progressContainer}>
            <View style={styles.progressBarTrack}>
              <View style={[styles.progressBarFill, { width: `${loadingProgress}%` }]} />
            </View>
            <Text style={styles.loadingText}>{loadingText}</Text>
          </View>
        )}

        {/* Cara Pakai */}
        <Text style={styles.sectionTitle}>Cara pakai</Text>

        <View style={styles.stepRow}>
          <View style={styles.stepNumber}>
            <Text style={styles.stepNumberText}>1</Text>
          </View>
          <View style={styles.stepTextBox}>
            <Text style={styles.stepTitle}>Salin link</Text>
            <Text style={styles.stepDesc}>Dari YouTube, TikTok, atau Instagram</Text>
          </View>
        </View>

        <View style={styles.stepRow}>
          <View style={styles.stepNumber}>
            <Text style={styles.stepNumberText}>2</Text>
          </View>
          <View style={styles.stepTextBox}>
            <Text style={styles.stepTitle}>Pilih format</Text>
            <Text style={styles.stepDesc}>MP3, MP4, WAV, dan lainnya</Text>
          </View>
        </View>

        <View style={styles.stepRow}>
          <View style={styles.stepNumber}>
            <Text style={styles.stepNumberText}>3</Text>
          </View>
          <View style={styles.stepTextBox}>
            <Text style={styles.stepTitle}>Simpan file</Text>
            <Text style={styles.stepDesc}>Langsung tersimpan ke HP kamu</Text>
          </View>
        </View>

        {/* Fitur */}
        <View style={styles.featureGrid}>
          <View style={styles.featureCard}>
            <Text style={styles.featureTitle}>Cepat</Text>
            <Text style={styles.featureDesc}>Proses dalam hitungan detik</Text>
          </View>
          <View style={styles.featureCard}>
            <Text style={styles.featureTitle}>Tanpa batas</Text>
            <Text style={styles.featureDesc}>Convert sepuasnya, gratis</Text>
          </View>
        </View>

        <Text style={styles.warningText}>
          ⚠ Pastikan kamu punya hak untuk mengunduh konten tersebut
        </Text>
      </View>
    </ScrollView>
  );
}

const RED = '#D8302B';
const DARK = '#111111';
const CARD_DARK = '#1C1C1C';

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: DARK,
  },
  scrollContent: {
    paddingBottom: 60,
  },
  hero: {
    width: '100%',
    minHeight: 380,
  },
  heroImage: {
    opacity: 0.85,
  },
  heroOverlay: {
    position: 'absolute',
    top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: RED,
    opacity: 0.38,
  },
  heroContent: {
    padding: 20,
    paddingTop: 50,
  },
  logoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 24,
  },
  logoBox: {
    width: 28,
    height: 28,
    borderRadius: 8,
    backgroundColor: DARK,
    alignItems: 'center',
    justifyContent: 'center',
  },
  logoIcon: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  logoText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
  heroLabel: {
    color: 'rgba(255,255,255,0.85)',
    fontSize: 12,
    marginBottom: 4,
  },
  heroTitle: {
    color: '#fff',
    fontSize: 26,
    fontWeight: '700',
    lineHeight: 32,
    marginBottom: 20,
  },
  tabRow: {
    flexDirection: 'row',
    backgroundColor: 'rgba(0,0,0,0.3)',
    borderRadius: 12,
    padding: 4,
    marginBottom: 12,
  },
  tab: {
    flex: 1,
    paddingVertical: 9,
    borderRadius: 9,
    alignItems: 'center',
  },
  tabActive: {
    backgroundColor: '#fff',
  },
  tabText: {
    fontSize: 13,
    color: '#fff',
    fontWeight: '500',
  },
  tabTextActive: {
    color: DARK,
  },
  urlBar: {
    backgroundColor: '#fff',
    borderRadius: 14,
    paddingVertical: 4,
    paddingHorizontal: 4,
  },
  urlInput: {
    fontSize: 13,
    color: '#1a1a1a',
    paddingVertical: 10,
    paddingHorizontal: 12,
  },
  uploadBar: {
    backgroundColor: '#fff',
    borderRadius: 14,
    paddingVertical: 14,
    paddingHorizontal: 14,
  },
  uploadBarText: {
    fontSize: 13,
    color: '#666',
  },
  body: {
    padding: 20,
  },
  sectionLabel: {
    fontSize: 13,
    color: '#999',
    marginBottom: 8,
  },
  formatGroupLabel: {
    fontSize: 11,
    color: '#777',
    marginBottom: 6,
    textTransform: 'uppercase',
  },
  formatGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 16,
  },
  formatButton: {
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#333',
    backgroundColor: CARD_DARK,
  },
  formatButtonActive: {
    backgroundColor: RED,
    borderColor: RED,
  },
  formatButtonText: {
    fontSize: 13,
    color: '#aaa',
    fontWeight: '500',
  },
  formatButtonTextActive: {
    color: '#fff',
  },
  convertButton: {
    backgroundColor: RED,
    paddingVertical: 16,
    borderRadius: 12,
    alignItems: 'center',
    marginTop: 8,
  },
  convertButtonDisabled: {
    backgroundColor: '#555',
  },
  convertButtonText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
  loadingText: {
    fontSize: 12,
    color: '#999',
    textAlign: 'center',
    marginTop: 8,
    lineHeight: 18,
  },
  progressContainer: {
    marginTop: 16,
  },
  progressBarTrack: {
    height: 6,
    backgroundColor: CARD_DARK,
    borderRadius: 3,
    overflow: 'hidden',
  },
  progressBarFill: {
    height: '100%',
    backgroundColor: RED,
    borderRadius: 3,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#fff',
    marginTop: 32,
    marginBottom: 16,
  },
  stepRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
    marginBottom: 14,
  },
  stepNumber: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: RED,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepNumberText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
  },
  stepTextBox: {
    flex: 1,
  },
  stepTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#fff',
  },
  stepDesc: {
    fontSize: 11,
    color: '#999',
    marginTop: 2,
  },
  featureGrid: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 16,
  },
  featureCard: {
    flex: 1,
    backgroundColor: CARD_DARK,
    borderRadius: 12,
    padding: 14,
  },
  featureTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#fff',
    marginBottom: 4,
  },
  featureDesc: {
    fontSize: 11,
    color: '#999',
  },
  warningText: {
    fontSize: 11,
    color: '#BA7517',
    textAlign: 'center',
    marginTop: 20,
  },
});
