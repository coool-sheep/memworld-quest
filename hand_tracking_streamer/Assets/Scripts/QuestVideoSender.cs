using System;
using System.IO;
using System.Net.Sockets;
using System.Text;
using UnityEngine;

public class QuestVideoSender : MonoBehaviour
{
    public event Action<string> OnError;

    private const uint FrameMagic = 0x4D414351; // "QCAM" little-endian
    private const uint MetadataMagic = 0x41544D51; // "QMTA" little-endian
    private const byte ProtocolVersion = 1;

    private TcpClient _tcpClient;
    private NetworkStream _networkStream;
    private BinaryWriter _writer;

    public bool Connect(string host, int port)
    {
        try
        {
            Disconnect();

            _tcpClient = new TcpClient(AddressFamily.InterNetwork);
            _tcpClient.NoDelay = true;
            _tcpClient.SendTimeout = 2000;
            _tcpClient.ReceiveTimeout = 2000;
            _tcpClient.Connect(host, port);
            _networkStream = _tcpClient.GetStream();
            _writer = new BinaryWriter(_networkStream);
            return true;
        }
        catch (Exception ex)
        {
            OnError?.Invoke($"Camera TCP connect failed: {host}:{port} {ex.Message}");
            Disconnect();
            return false;
        }
    }

    public bool SendFrame(byte[] jpegBytes, uint frameId, ulong timestampNs, int width, int height)
    {
        if (jpegBytes == null || jpegBytes.Length == 0)
        {
            OnError?.Invoke("Camera TCP send aborted: frame payload is empty.");
            return false;
        }

        if (_writer == null || _networkStream == null || !_networkStream.CanWrite)
        {
            OnError?.Invoke("Camera TCP send aborted: transport is not writable.");
            return false;
        }

        try
        {
            _writer.Write(FrameMagic);
            _writer.Write(ProtocolVersion);
            _writer.Write((byte)0);
            _writer.Write((ushort)Mathf.Clamp(width, 0, ushort.MaxValue));
            _writer.Write((ushort)Mathf.Clamp(height, 0, ushort.MaxValue));
            _writer.Write((byte)0);
            _writer.Write((byte)0);
            _writer.Write(frameId);
            _writer.Write(timestampNs);
            _writer.Write(jpegBytes.Length);
            _writer.Write(jpegBytes);
            _writer.Flush();
            return true;
        }
        catch (Exception ex)
        {
            OnError?.Invoke($"Camera TCP send failed: {ex.Message}");
            Disconnect();
            return false;
        }
    }

    public bool SendMetadataJson(string metadataJson)
    {
        if (string.IsNullOrWhiteSpace(metadataJson))
        {
            OnError?.Invoke("Camera metadata send aborted: payload is empty.");
            return false;
        }

        if (_writer == null || _networkStream == null || !_networkStream.CanWrite)
        {
            OnError?.Invoke("Camera metadata send aborted: transport is not writable.");
            return false;
        }

        try
        {
            byte[] payload = Encoding.UTF8.GetBytes(metadataJson);
            _writer.Write(MetadataMagic);
            _writer.Write(ProtocolVersion);
            _writer.Write((byte)0);
            _writer.Write((ushort)0);
            _writer.Write((uint)payload.Length);
            _writer.Write(payload);
            _writer.Flush();
            return true;
        }
        catch (Exception ex)
        {
            OnError?.Invoke($"Camera metadata send failed: {ex.Message}");
            Disconnect();
            return false;
        }
    }

    public void Disconnect()
    {
        try
        {
            _writer?.Close();
        }
        catch { }
        finally
        {
            _writer = null;
        }

        try
        {
            _networkStream?.Close();
        }
        catch { }
        finally
        {
            _networkStream = null;
        }

        try
        {
            _tcpClient?.Close();
        }
        catch { }
        finally
        {
            _tcpClient = null;
        }
    }

    private void OnDestroy()
    {
        Disconnect();
    }
}
