export type Product = {
  id?: string;
  name?: string;
  title?: string;
  image?: string;
  price?: number | string;
  regularPrice?: number | string;
  clearancePrice?: number | string;
  storeName?: string;
  storeId?: string | number;
  url?: string;
  [key: string]: any;
};
