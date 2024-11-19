import { Configuration, DefaultApi } from './clients/typescript';

const config = new Configuration({
  basePath: 'http://localhost:8000',
});

const api = new DefaultApi(config);

async function main() {
  try {
    // 登入
    const loginResult = await api.loginApiV1LoginPost();
    console.log('登入結果:', loginResult);

    // 搜尋
    const searchResult = await api.searchBulletinsApiV1SearchPost({
      startDate: '2024-03-20',
      endDate: '2024-03-20',
    });
    console.log('搜尋結果:', searchResult);
  } catch (error) {
    console.error('發生錯誤:', error);
  }
}

main();
