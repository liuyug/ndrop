@echo off

echo ��ǰ�豸��
platform-tools\adb devices
echo ��ǰ IP ��ַ
platform-tools\adb shell "ip a | grep 'inet 1'"

echo �������
echo platform-tools\adb tcpip 5555
echo platform-tools\adb connect ip:5555
echo platform-tools\adb devices

echo ������� "ip:5555    offline"��������
echo ���ֻ����ã�������ģʽ������"�����ģʽ������ADB����"������"USB����"
echo Ȼ���ٴ����в鿴
echo platform-tools\adb devices
